# -*- coding: utf-8 -*-
# @Time    : 2021/2/4 22:09
# @Author  : hushhw
# @Software: PyCharm
# @FileName: index.py

import os
from collections import Counter
import requests
import datetime
import time
import re
import jieba
import math
from os.path import join as pjoin
import json
from flask import Flask, jsonify, request
from flask import render_template
from concurrent.futures import ThreadPoolExecutor
from celery import Celery
from celery.schedules import crontab

mid = {'aotu':'36909511', 'yenong':'327552140'}

# 创建线程池执行器
executor = ThreadPoolExecutor()
aotudata = Flask(__name__)

celery = Celery(aotudata.name, backend='redis://localhost:6379/0', broker='redis://localhost:6379/0')

celery.conf.timezone = "Asia/Shanghai"
celery.conf.update(
    CELERYBEAT_SCHEDULE={
        'add_task': {
            'task': 'index.add',
            'schedule': crontab(minute='*/10'),
            'args': (1, 1)
        },
        'danmu_task': {
            'task': 'index.get_newdanmu_info',
            'schedule': crontab(0, 0,day_of_month='*/2')
        },
        'fans_task': {
            'task': 'index.get_fansnum_info',
            'schedule': crontab(minute=59, hour='*/1'),
        },
    }
)

@celery.task
def get_wordcloud_info(mid):
    stop_words = []
    for line in open('static/data/stop_words.txt', 'r', encoding='gbk'):
        if line.strip() not in stop_words:
            stop_words.append(line.strip())
    # 加载自定义词典
    jieba.load_userdict(r'static/data/user_dict.txt')
    filepath = 'static/data/'+mid
    with open(filepath + '/result.txt', encoding='utf-8') as f:
        mytext = f.read()
    mytext = re.sub(r"[\s+\.\!\/_,$%^*(+\"\']+|[+——！，。？、~@#￥%……&*（）]+", "", mytext)
    wl_space_split = " ".join([str(item) for item in jieba.cut(mytext, cut_all=False) if item not in stop_words])
    words = wl_space_split.split(' ')
    counter = Counter(words)
    wordcloud = {}
    for fre in counter.most_common(50):
        key = str(str(fre).split("'")[1])
        value = int(str(fre).split(' ')[1].split(')')[0])
        wordcloud[key] = value
    wordcloudjson = json.dumps(wordcloud, ensure_ascii=False)
    return wordcloudjson

@celery.task
def get_fans_info(mid):
    d_time = []
    d_num = []
    num = 0
    output_dir = 'static/data/' + mid
    listdir = os.listdir(output_dir)
    model = dict()
    if 'follower.json' in listdir:
        fr = open(pjoin(output_dir, 'follower.json'))
        model = json.load(fr)
        fr.close()
    lastvalue = 0
    for key, value in model.items():
        num += 1
        d_time.append(key)
        d_num.append(int(value) - lastvalue)
        lastvalue = int(value)
    if num > 30:
        result = dict(zip(d_time[-30:], d_num[-30:]))
        fansnumjson = json.dumps(result, ensure_ascii=False)
        return fansnumjson
    else:
        result = dict(zip(d_time[1:], d_num[1:]))
        fansnumjson = json.dumps(result, ensure_ascii=False)
        return fansnumjson

@celery.task
def add(x, y):
    return x+y

@celery.task
def get_fansnum_info():
    output_dir = 'static/data'
    for path, dir_list, file_list in os.walk(output_dir):
        for middir in dir_list:
            mid = str(middir)
            base_info_url = f'https://api.bilibili.com/x/relation/stat?vmid={mid}'
            dic_header = {'User-Agent': 'Mozilla/5.0'}
            base_info = requests.get(base_info_url, headers=dic_header).json()['data']
            follower = base_info['follower']
            today = datetime.date.today().strftime('%y/%m/%d')
            listdir = os.listdir(path + '/' + middir)
            if 'follower.json' in listdir:
                fr = open(pjoin(path + '/' + middir, 'follower.json'))
                model = json.load(fr)
                fr.close()
                model[today] = follower
                jsobj = json.dumps(model)
                with open(pjoin(path + '/' + middir, 'follower.json'), "w") as fw:
                    fw.write(jsobj)
                    fw.close()
            else:
                with open(pjoin(path + '/' + middir, 'follower.json'), "w") as fw:
                    model = dict()
                    model[today] = follower
                    jsobj = json.dumps(model)
                    fw.write(jsobj)
                    fw.close()

@celery.task
def get_newdanmu_info():
    output_dir = 'static/data'
    for path, dir_list, file_list in os.walk(output_dir):
        for middir in dir_list:
            mid = str(middir)
            base_info = get_base_info(mid)
            page_number = math.ceil(base_info['archive_count'] / 100)
            vlist = []
            for pnum in range(page_number):
                get_vlist_info(mid, pnum + 1, vlist)
            print("爬取最新弹幕")
            # 由于api请求过多会限制请求，所以考虑只对最新发布的视频追加弹幕数据，按照月份来存储，只更新近两个月的投稿
            # 新的弹幕按照月份进行更新，进更新近两个月的
            beforetwomonth = int(time.mktime(datetime.date(datetime.date.today().year, datetime.date.today().month-1, 1).timetuple()))
            beginmonth = int(time.mktime(datetime.date(datetime.date.today().year, datetime.date.today().month, 1).timetuple()))
            print(beforetwomonth, beginmonth)
            if os.path.exists(path + '/' + middir + '/' + str(beforetwomonth)+'.txt') is True:
                os.remove(path + '/' + middir + '/' + str(beforetwomonth)+'.txt')
            if os.path.exists(path + '/' + middir + '/' + str(beginmonth) + '.txt') is True:
                os.remove(path + '/' + middir + '/' + str(beginmonth) + '.txt')
            num = 0
            for v in vlist:
                if int(v['created']) > beforetwomonth and int(v['created']) < beginmonth:
                    num += 1
                    print(v['bvid'], num)
                    danmu = get_onedanmu_info(v['bvid'])
                    with open(path + '/' + middir + '/danmu'+ str(beforetwomonth)+'.txt', 'a+', encoding='utf-8') as f:
                        f.write(v['bvid'] + '\n')
                        for con in danmu:
                            data = re.sub(r'\[.*\]', '', con) # 去掉表情
                            data = re.sub(r'哈哈哈+', '', data) # up猫叫哈哈，不得不把哈哈哈哈。。。判掉
                            f.write(data + '\n')
                elif int(v['created']) > beginmonth:
                    num += 1
                    print(v['bvid'], num)
                    danmu = get_onedanmu_info(v['bvid'])
                    print(danmu[0])
                    with open(path + '/' + middir + '/danmu' + str(beginmonth) + '.txt', 'a+', encoding='utf-8') as f:
                        f.write(v['bvid'] + '\n')
                        for con in danmu:
                            data = re.sub(r'\[.*\]', '', con)  # 去掉表情
                            data = re.sub(r'哈哈哈+', '', data)  # up猫叫哈哈，不得不把哈哈哈哈。。。判掉
                            f.write(data + '\n')
            danmufile = []
            filepath = path + '/' + middir
            f_list = os.listdir(filepath)
            for i in f_list:
                if os.path.os.path.splitext(i)[0].startswith('danmu'):
                    danmufile.append(i)
            resultfile = open(filepath + '/result.txt', 'w', encoding='utf-8')
            for file in danmufile:
                for line in open(filepath + '/' + file, encoding='utf-8'):
                    resultfile.writelines(line)
                resultfile.write('\n')

def get_base_info(mid):
    base_info_url = f'https://api.bilibili.com/x/web-interface/card?mid={mid}'
    dic_header = {'User-Agent': 'Mozilla/5.0'}
    base_info = requests.get(base_info_url, headers = dic_header).json()['data']
    return base_info

def get_vlist_info(mid, pnum, vlist):
    base_info_url = f'https://api.bilibili.com/x/space/arc/search?mid={mid}&ps=100&tid=0&pn={pnum}'
    dic_header = {'User-Agent': 'Mozilla/5.0'}
    base_info = requests.get(base_info_url, headers=dic_header).json()['data']
    for v in base_info['list']['vlist']:
        vlist.append(v)

def get_month_info(vlist):
    monthbegin = int(time.mktime(datetime.date(datetime.date.today().year, datetime.date.today().month, 1).timetuple()))
    monthupdate = 0
    for v in vlist:
        if int(v['created']) > monthbegin:
            monthupdate += 1
        else:
            break
    return monthupdate

def get_updatetime_info(vlist):
    latesttime = time.localtime(vlist[0]['created'])
    dt1 = time.strftime("%Y-%m-%d %H:%M:%S", latesttime)
    date1 = datetime.datetime.strptime(dt1, "%Y-%m-%d %H:%M:%S").date()
    recenttime = time.localtime(time.time())
    dt2 = time.strftime("%Y-%m-%d %H:%M:%S", recenttime)
    date2 = datetime.datetime.strptime(dt2, "%Y-%m-%d %H:%M:%S").date()
    vday = (date2-date1).days
    return vday

def get_rank_info(mid):
    base_info_url = f'https://api.bilibili.com/x/space/arc/search?mid={mid}&ps=100&tid=0&pn=1&order=click'
    dic_header = {'User-Agent': 'Mozilla/5.0'}
    rank_info = requests.get(base_info_url, headers=dic_header).json()['data']
    vinfo = []
    maxclick = int(rank_info['list']['vlist'][0]['play'])

    for num in range(0,8):
        midhref = 'https://www.bilibili.com/video/' + rank_info['list']['vlist'][num]['bvid']
        vinfo.append([num+1, midhref, rank_info['list']['vlist'][num]['title'], rank_info['list']['vlist'][num]['play'], int(rank_info['list']['vlist'][num]['play'])/maxclick * 100])
    return vinfo

def get_contribute_info(vlist):
    vinfo = []
    for num in range(0, 8):
        vid = vlist[num]['bvid']
        vtitle = vlist[num]['title']
        createtime = time.localtime(vlist[num]['created'])
        dt = time.strftime("%Y-%m-%d %H:%M:%S", createtime)
        vtime = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S").date()
        vlength = vlist[num]['length']
        base_info_url = f'https://api.bilibili.com/x/web-interface/archive/stat?bvid={vid}'
        dic_header = {'User-Agent': 'Mozilla/5.0'}
        base_info = requests.get(base_info_url, headers=dic_header).json()['data']
        vinfo.append([num+1, vtitle, base_info['view'], vtime, vlength, base_info['reply'], base_info['danmaku'], base_info['like'], base_info['coin'], base_info['favorite']])
    return vinfo

def get_onedanmu_info(vid):
    get_oid_url = f'https://api.bilibili.com/x/player/pagelist?bvid={vid}'
    dic_header = {'User-Agent': 'Mozilla/5.0'}
    get_oid_info = requests.get(get_oid_url, headers=dic_header).json()['data']
    oid = get_oid_info[0]['cid']
    get_danmu_url = f'https://api.bilibili.com/x/v1/dm/list.so?oid={oid}'
    get_danmu_info = requests.get(get_danmu_url, headers=dic_header)
    get_danmu_info.encoding = 'utf-8'
    data = re.findall('<d p=".*?">(.*?)</d>', get_danmu_info.text)
    return data

def get_olddanmu_info(mid, vlist):
    if os.path.exists('static/data/'+mid+'/danmu_old.txt') is True:
        return
    print("爬取两个月前的弹幕")
    beforetwomonth = int(time.mktime(datetime.date(datetime.date.today().year, datetime.date.today().month-1, 1).timetuple()))
    num = 0
    for v in vlist:
        if int(v['created']) < beforetwomonth:
            num += 1
            print(v['bvid'], num)
            danmu = get_onedanmu_info(v['bvid'])
            with open('static/data/'+mid+'/danmu_old.txt', 'a+', encoding='utf-8') as f:
                f.write(v['bvid']+'\n')
                for con in danmu:
                    data = re.sub(r'\[.*\]', '', con) # 去掉表情
                    data = re.sub(r'哈哈哈+', '', data) # up猫叫哈哈，不得不把哈哈哈哈。。。判掉
                    f.write(data + '\n')

@aotudata.route('/wordcloudtask', methods=['POST'])
def wordcloudtask():
    arg = request.get_json(force=True)
    upmid = mid[arg['up'].split('/')[1]]
    task = get_wordcloud_info.apply_async(args=[upmid,])
    return jsonify(task.get()), 202, {'Location': task.task_id}

@aotudata.route('/fansnumtask', methods=['POST'])
def fansnumtask():
    arg = request.get_json(force=True)
    upmid = mid[arg['up'].split('/')[1]]
    task = get_fans_info.apply_async(args=[upmid,])
    return jsonify(task.get()), 202, {'Location': task.task_id}

@aotudata.route('/')
def index():
    return render_template('index.html')

@aotudata.route('/aotu')
def aotu():
    base_info = get_base_info(mid['aotu'])
    upname = base_info['card']['name']
    page_number = math.ceil(base_info['archive_count'] / 100)
    vlist = []
    for pnum in range(page_number):
        get_vlist_info(mid['aotu'], pnum + 1, vlist)
    monthupdate = get_month_info(vlist)
    vday = get_updatetime_info(vlist)
    overview_list = [vday, monthupdate, base_info['archive_count']]
    rank_list = get_rank_info(mid['aotu'])
    constribute_list = get_contribute_info(vlist)
    if not os.path.exists('static/data/' + mid['aotu']):
        os.makedirs('static/data/' + mid['aotu'])
    get_olddanmu_info(mid['aotu'], vlist)
    return render_template('cuigeng.html', upname = upname, overviewlist = overview_list, ranklist = rank_list,
                           constributelist = constribute_list)

@aotudata.route('/yenong')
def yenong():
    base_info = get_base_info(mid['yenong'])
    upname = base_info['card']['name']
    page_number = math.ceil(base_info['archive_count'] / 100)
    vlist = []
    for pnum in range(page_number):
        get_vlist_info(mid['yenong'], pnum + 1, vlist)
    monthupdate = get_month_info(vlist)
    vday = get_updatetime_info(vlist)
    overview_list = [vday, monthupdate, base_info['archive_count']]
    rank_list = get_rank_info(mid['yenong'])
    constribute_list = get_contribute_info(vlist)
    if not os.path.exists('static/data/' + mid['yenong']):
        os.makedirs('static/data/' + mid['yenong'])
    get_olddanmu_info(mid['yenong'], vlist)
    return render_template('cuigeng.html', upname = upname, overviewlist = overview_list, ranklist = rank_list,
                           constributelist = constribute_list)


if __name__ == '__main__':
    aotudata.run(debug=True)