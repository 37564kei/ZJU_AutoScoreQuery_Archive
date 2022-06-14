import requests
import json
import re
import datetime
import time
import sys
import pandas
import lxml
import smtplib
import threading
from email.mime.text import MIMEText
from email.header import Header

def dft2(sess, headers):
    try:
        sess.get('http://jwbinfosys.zju.edu.cn/default2.aspx', headers=headers)
    except:
        pass
	
class ScoreQuery(object):
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.login_url = "https://zjuam.zju.edu.cn/cas/login?service=http://jwbinfosys.zju.edu.cn"
        self.base_url = "http://jwbinfosys.zju.edu.cn/xscj.aspx?xh=" + username
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36",
            'Connection': 'close'
        }
        self.sess = requests.Session()
        print(username)
        print(password)
    
    def login(self):
        """Login to ZJU platform"""
        res = self.sess.get(self.login_url, headers=self.headers)
        execution = re.search(
            'name="execution" value="(.*?)"', res.text).group(1)
        res = self.sess.get(
            url='https://zjuam.zju.edu.cn/cas/v2/getPubKey', headers=self.headers).json()
        n, e = res['modulus'], res['exponent']
        encrypt_password = self._rsa_encrypt(self.password, e, n)

        data = {
            'username': self.username,
            'password': encrypt_password,
            'execution': execution,
            '_eventId': 'submit'
        }
        res = self.sess.post(url=self.login_url, data=data, headers=self.headers)

        # check if login successfully
        try:
            dec = res.content.decode()
            if '统一身份认证' in dec:
                raise LoginError('登录失败，请核实账号密码重新登录')
        except Exception as err:
            pass
        
        return self.sess
        
    def _rsa_encrypt(self, password_str, e_str, M_str):
        password_bytes = bytes(password_str, 'ascii')
        password_int = int.from_bytes(password_bytes, 'big')
        e_int = int(e_str, 16)
        M_int = int(M_str, 16)
        result_int = pow(password_int, e_int, M_int)
        return hex(result_int)[2:].rjust(128, '0')
        
    def getInfo(self):
        trialCount = 0
        while trialCount < 10:
            thread = threading.Thread(target = dft2, args = (self.sess, self.headers))
            thread.start()
            time.sleep(1)
            
            res = self.sess.get(self.base_url, headers = self.headers)
            html = res.content.decode('gb2312')

            matchResult = re.search('name="__VIEWSTATE" value="(.*?)"', res.text)
            if (str(matchResult) != 'None'):
                break
            trialCount += 1
            print("[log] 尝试读取数据失败，尝试第 " + str(trialCount) + " 次")
        
        if str(matchResult) == 'None':
            exit('[Error] 读取数据失败。')
        self.viewstate = matchResult.group(1)
        
        data = {
            '__VIEWSTATE': self.viewstate,
            'ddlXN': '',
            'ddlXQ': '',
            'txtQSCJ': '',
            'txtZZCJ': '',
            'Button2': '%D4%DA%D0%A3%D1%A7%CF%B0%B3%C9%BC%A8%B2%E9%D1%AF'
        }
        res = self.sess.post(url=self.base_url, data=data, headers=self.headers)
        html = res.text

        return html
        
class LoginError(Exception):
    """Login Exception"""
    pass
    
def myHash(text:str):
   hash = 0
   for ch in text:
      hash = (hash * 281 ^ ord(ch) * 997) & 0xFFFFFFFF
   return hash

def sendMsg(newRecords, mailto, mailfrom, key):
    host = "smtp.163.com"
    port = 25
    sender = mailfrom
    receivers = [mailto]
    
    msg = MIMEText(newRecords, 'plain', 'utf-8')
    msg['From'] = Header("auto_score_query@xuanInsr")
    msg['To'] = Header(mailto)
    
    subject = '出分啦！'
    msg['Subject'] = Header(subject, 'utf-8')
    
    try:
        smtpObj = smtplib.SMTP()
        smtpObj.connect(host, port)
        smtpObj.login(sender, key)
        smtpObj.sendmail(sender, receivers, msg.as_string())
        print("[status] 邮件已发送！")
    except Exception as err:
        print("[error] 邮件发送失败: " + str(err))
    

def main(username, password, mailto, mailfrom, key):
    print("[status] 初始化...")
    scoreQuery = ScoreQuery(username, password)
    
    print("[status] 登录...")
    try:
        scoreQuery.login()
    except Exception as err:
        print(str(err))
        raise Exception
        
    print("[status] 获取数据...")
    firstTry = 1
    try:
        res = scoreQuery.getInfo()
    except Exception as err:
        print(str(err))
        raise Exception
    
    print("[status] 处理数据...")
    data = pandas.read_html(res)
    newData = {k: str(v).split()[8:] for k, v in data[2].groupby(0)}
    del newData['选课课号']
    newRecords = ''
    try:
        print("> 读取成绩记录列表...")
        f = open("log.txt", "r")
        
        s = f.read()
        records = set(s.split())
        f.close()
            
        print("> 对比记录更新...")
        for k, v in newData.items():
            if str(myHash(k)) not in records:
                newRecord = "课程名: " + v[0] + " 成绩: " + v[1] + " 学分: " + v[2] + " 绩点: " + v[3]
                newRecords += '\n' + newRecord
                print("    [!] 发现新记录: " + newRecord)
        print("> 对比结束")
    except Exception as err:
        # first time
        print(str(err))
        print("[!] 此前暂无记录，正在生成首次记录...")
        
    tryCount = 5
    while len(newRecords) != 0 and tryCount > 0:
        try:
            print("> 尝试发送邮件...")
            sendMsg(newRecords, mailto, mailfrom, key)
            break
        except Exception as err:
            print("[Error] 发送失败: " + str(err))
            tryCount -= 1
    
    if tryCount == 0:
        print("[Error] 发送失败。")
        exit(1)
        
    print("[status] Writing data...")
    f = open("log.txt", "w")
    for k, v in newData.items():
        #print(k, ":", v)
        f.write(str(myHash(k)) + ' ')
        #print(myHash(k))
    f.close()

if __name__ == "__main__":
    username = sys.argv[1]
    password = sys.argv[2]
    mailto = sys.argv[3]
    mailfrom = sys.argv[4]
    key = sys.argv[5]
    try:
        main(username, password, mailto, mailfrom, key)
    except Exception as err:
        print(str(err))
