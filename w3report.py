#!/usr/bin/env python
# coding=utf8
#
# Last Change Date: Mon, 04 Sep 2017 17:10:58 +0800
# by Jackson
#
# to get users CPU log for US Perf
# need xlwt support


import urllib2, re, sys, traceback
from datetime import datetime, timedelta
import Queue
from threading import Thread, RLock
import xlwt
import random, time


UserThreadNum = 3
DailyThreadNum = 10
#texc = 'datetime.now().strftime("%X")'

###
#  class ThreadRunner, implement worker threads,
#          passing two Queues for done and undo
###
class ThreadRunner(Thread):
    def __init__(self, workQueue, resultQueue):
        Thread.__init__(self)
        self.timeout = 5
        self.workQueue = workQueue
        self.resultQueue = resultQueue
        self.start()

    def run(self):
        while True:
            try:
                curwork = self.workQueue.get(timeout=self.timeout)
                curwork.run()
                self.resultQueue.put(curwork)
            except Queue.Empty:
                break
            except:
                print traceback.print_exc()

###
#  class ThreadPool, initial all the threads, waiting for complete
###

class ThreadPool:
    def __init__(self, num=10, name='Threading'):
        self.workQueue = Queue.Queue()
        self.resultQueue = Queue.Queue()
        self.threads = []
        self.name = name
        self.__createThreadPool(num)

    def __createThreadPool(self, num):
        for i in range(num):
            thread = ThreadRunner(self.workQueue, self.resultQueue)
            self.threads.append(thread)

    def waitComplete(self, timeout=60):
        while len(self.threads):
            time.sleep(random.random()*5)
            thread = self.threads.pop()
            if thread.isAlive():
                thread.join()

    def add_job(self, job):
        self.workQueue.put(job)

###
#  Class LPAR, process per LPAR, this create thread(s) for one or more USER
#     and writing data to a sheet named by the LPAR
###

class LPAR:
    def __init__(self, lparid, daterange, wb, uth_num=UserThreadNum, dth_num=DailyThreadNum):
        self.id = int(lparid)
        self.daterange = daterange
        self.uth = uth_num
        self.dth = dth_num
        self.link = "http://pkmfgvm4.pok.ibm.com/~PERFDOC/LNXVM%s.html" % self.id
        self.users = []
        self.lparlog = []
        self.ulogs = {}
        self.__getusers()
        self.ws = wb.add_sheet("LNXVM%s" % self.id)
        self.result = {}

    def __getusers(self):
        print "reading users from LNXVM%s..." % self.id
        content = urllib2.urlopen(self.link)
        # USER ID list, type list, ordered
        self.users = re.compile(r'PKMFGVM4.POK.IBM.COM/~PERFDOC/([A-Z0-9]{8})', re.S).findall(content.read())
        content.close()
        self.users.sort()
        print self.users

    def run(self):
        tp = ThreadPool(self.uth, "LPAR%s" % self.id)
        for u in self.users:
            tp.add_job(User(self.id, self.daterange, u, self.dth))
        tp.waitComplete()
        while not tp.resultQueue.empty():
            cur = tp.resultQueue.get()
            self.result[cur.record[0]] = cur.record[1]
        print "Almost done, writing xls"
        self.writingxls()

    def writingxls(self):
        ### write data to xls
        col = 3
        style = xlwt.easyxf(num_format_str='0.00')
        for r in self.users:
            row = 0
            self.ws.write(row, col, r)
            for i in self.result[r]:
                row += 1
                try:
                    self.ws.write(row, col, i[2], style)
                except ValueError:
                    print i
                    print traceback.print_exc()
            col += 1
        ### write date, time and total
        dcol = 0
        tcol = 1
        tocol = 2
        self.ws.write(0, dcol, "Date")
        self.ws.write(0, tcol, "Time")
        self.ws.write(0, tocol, "Total")
        row = 1

        sampleUser = ""
        for u in self.users:
            if len(self.result[u]) == 0:
                pass
            else :
                sampleUser = u
                break

        for r in self.result[sampleUser]:  # read date and time from sample user
            try:
                self.ws.write(row, dcol, r[0])
                self.ws.write(row, tcol, r[1])
                num = len(self.users)
                if num < 23:
                    endcol = chr(67 + num)
                else:
                    endcol = chr(64 + num/26) + chr(64 + (num + 3) % 26)
                self.ws.write(row, tocol, xlwt.Formula("SUM(%s%s:%s%s)" % (chr(68), row+1, endcol, row+1)), style)
            except ValueError:
                print traceback.print_exc()
            row += 1

###
#   Class User, process each User's log, can be created for multi-threading
#        by class LPAR
###
class User:
    def __init__(self, lparid, daterange, userid, dth_num=DailyThreadNum):
        self.lparid =    lparid
        self.daterange = daterange # start&end time tuple
        self.name =      userid
        self.dthu =      dth_num

    def run(self):
        print "retrieving userdata for %s on LNXVM%s" % (self.name, self.lparid)
        start, end = self.daterange
        tp = ThreadPool(self.dthu, self.name)
        i = start
        c = 0
        while i <= end:
            tp.add_job(dailylog(self.lparid, self.name, i.strftime("%Y%m%d"),c))
            i = i + timedelta(1)
            c += 1
        tp.waitComplete()
        ###
        #  Result Processing here
        ###
        readylist = []
        while not tp.resultQueue.empty():
            readylist.append(tp.resultQueue.get())
        readylist.sort(key=lambda dailylog: dailylog.id)
        usercolumn = []
        for dl in readylist:
            for k in dl.avg.keys():
                if k > 9:
                    usercolumn.append((dl.date, str(k),     dl.avg[k]))
                else:
                    usercolumn.append((dl.date, "0"+str(k), dl.avg[k]))
        self.record = (self.name, usercolumn)
        print "Userdata %s done" % self.name


###
#  Class dailylog, base runner for data, one link one day on user
#      process every single day's data, multi-threading by class User
###
class dailylog():
    def __init__(self, lpar, userid, date, id=-1):
        self.lpar = lpar
        self.id = id
        self.userid = userid
        self.date = date # string type time
        self.record = []
        self.avg = {}
        for i in range(0, 24):
            self.avg[i] = 0
        baselink = "http://pkmfgvm4.pok.ibm.com/~PERFDOC/htbin/lnxulog?"
        target = "12%s+%s+%s" % (self.lpar, self.userid, self.date)
        self.url = baselink + target

    def run(self):
        retry = 1
        while True:
            try:
                link = urllib2.urlopen(url=self.url, timeout=60)
                result = link.read()
                content = re.compile(r'Mean.*?<hr>', re.S).search(result).group()
                break
            except AttributeError:
                content = re.compile(r'No data available', re.S).search(result)
                if content:
                    print "%s not logged at %s" % (self.userid, self.date)
                link.close()
                return
            except urllib2.HTTPError, e:
                print "Fail reading data on %s %s" % (self.userid, self.date)
                link.close()
                return
            except urllib2.URLError:
                print "timeout occured while dealing with %s at %s, reconnecting for %s time(s)" % (self.userid, self.date, retry)
                time.sleep(retry+random.random()*4)
                retry += 2
                if retry > 6:
                    print "timeout retry after three times, aborted"
                    link.close()
                    return
        for c in content.split('\r\n')[1:-1]:
            try:
                r = re.compile(r'(\d+):\d+:\d+\s+(\d+\.\d*|\d+|\.\d+)').search(c).groups()
                self.record.append(r)
                # self.record tuple (time, cpu)
            except:
                print "Parsing error at %s: %s >>> %s" % (self.userid, self.date, c)
        try:
            f = open("/tmp/%s.%s" % (self.userid, self.date), 'w')
            for i in self.record:
                print >> f, "%s %s %s" % (self.date, i[0], i[1])
            f.close()
        except:
            pass
        for i in self.record:
            try:
                hour = int(i[0])
            except ValueError:
                continue
            try:
                self.avg[hour] += float(i[1])
            except ValueError:
                print i
                self.avg[key] += 0.0
        for i in range(1, 23):
            self.avg[i] /= 12
        self.avg[23] /=8
        self.avg[0] /=10

if __name__=="__main__":
    print "     \033[1;32m** W3C report, last update: Aug 1 2017 **\033[0m"
    while True:
        print "which LPAR(s) would be process: separate by space ' '"
        lpars = sys.stdin.readline().strip()
        if not re.compile(r'^\d{1,2}( \d{1,2})*$').match(lpars):
            print "LPAR not valid"
        else:
            break
    while True:
        print "the Date range, like \"YYYYMMDD-YYYYMMDD\"(no quote):"
        daterange = sys.stdin.readline().strip()
        if not re.compile(r'^(\d{8}-\d{8})|(\d{8})$').match(daterange):
            print "invalid daterange"
            continue
        try:
            se = re.compile(r'-').split(daterange)
            if len(se) == 2:
                start, end = (datetime.strptime(se[0], "%Y%m%d"), datetime.strptime(se[1],"%Y%m%d"))
            else:
                start, end = (datetime.strptime(se[0], "%Y%m%d"), datetime.strptime(se[0],"%Y%m%d"))
            daterange = (start, end)
            break
        except:
            print "invalid daterange"
    while True:
        print "how many threads would be set for processing Users(default = 2):"
        i_tnu = sys.stdin.readline().strip()
        print "how many threads would be set for processing each user's dailylog(default = 10):"
        i_tnd = sys.stdin.readline().strip()
        pat = re.compile(r'^\d+$')
        valid = True
        if i_tnu == '':
            i_tnu = 2
        if i_tnd == '':
            i_tnd = 10
        if pat.match(str(i_tnu)) and pat.match(str(i_tnd)):
            if int(i_tnu)*int(i_tnd) >= 40:
                print "too many threads will be create, is it OK? y/n"
                f = sys.stdin.readline().strip()
                if not re.match(r'^(y|Y)$', f):
                    valid = False
                else:
                    valid = True
        else:
            print "invalid thread num"
            valid = False
        if valid:
            break
    lpars = re.compile(r'\s+').split(lpars)
    wb = xlwt.Workbook()
    for lpar in lpars:
        LPAR(lpar, daterange, wb, int(i_tnu), int(i_tnd)).run()
wb.save('template.xls')
