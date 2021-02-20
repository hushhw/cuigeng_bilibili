# B 站 UP 催更网页



仿照影视飓风的投稿《[【画质改造】48小时爆改党妹的家！](https://www.bilibili.com/video/BV1pz4y1S7t7)》中的催更网页制作。

参考：https://cuigeng.hushhw.cn/aotu

![](https://photo.hushhw.cn/img2021/cuigeng_aotu.png)



### 配置

使用 Flask + celery+redis 完成，运行时使用 celery 来异步在后台定时爬取更新数据，故在运行 Flask 的同时，需要运行celery 的 worker 和 beat 任务。

运行 celery：

```
# linux系统
celery worker -A index -l INFO -B
# windows系统，无法同时启动beat，需分开
celery worker -A index -l INFO
celery beat -A index -l INFO
```

配置到远程服务器，参考：https://cloud.tencent.com/developer/article/1355803



### 数据来源

数据从 B 站爬取，由于 B 站对访问的限制，故不可以频繁访问，短期内频繁访问会被拒绝访问，短期内会恢复。

* `总排行榜` 和 `已投稿视频列表` 刷新页面即更新
* `粉丝变化` 每一小时异步更新一次
* `云图数据` 为爬取弹幕数据，使用 `jieba` 分词后统计出，每两天异步更新一次



### 使用说明

* 拓展新的 up，需要在 `index.py` 中添加 mid 到 `mid` 字典，默认为

  ```
  mid = {'aotu':'36909511', 'yenong':'327552140'}
  ```

  up 的 mid 为主页的 url 后缀，如：https://space.bilibili.com/36909511/，后续异步获取数据都需要通过该 dict 获取 mid 来获取数据。

* 随后需要在 `index.py` 中添加新 up 的页面配置，参考默认的 `aotu` 和 `yenong`，仅需修改 url 标识以及 mid 值，参考：

  ```python
  @aotudata.route('/aotu')
  def aotu():
      base_info = get_base_info(mid['aotu'])
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
      return render_template('cuigeng.html', overviewlist = overview_list, ranklist = rank_list, constributelist = constribute_list)
  ```

* 初次运行后，会在 `static/data` 下创建以 mid 为名的文件夹，后续更新数据都会存储在此

* 分词去停用词在 `static/data/stop_words.txt` 中添加，分词用户词典在 `static/data/user_dict.txt` 中添加



### TODO

* 优化添加新 up 的代码逻辑，不再是复制新的 route
* 优化加载速度



### 其他

第一次学习使用 Flask+celery，借此作为一个练习。



