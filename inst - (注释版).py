# _*_coding:utf8 _*_
import re
import os
import sys
import time
import jieba
import thread
import urllib
from models import DoubanUser, DoubanUserAccessUrl, DoubanMovie, DoubanMovieNewest, DoubanCast, DoubanDirector, DoubanGenre, DoubanUserAction, DoubanUserInterest, DoubanUserRecommend

DOMAIN_NUM = 4
MOVIE_DOMAIN = 0
DIRECTOR_DOMAIN = 1
ACTOR_DOMAIN = 2
GENRE_DOMAIN = 3

SEARCH_ACTION = 0
ACCESS_ACTION = 1
RELATE_ACTION = 2

ACTION_TYPE_TO_DEGREE = [1.0, 1.0, 0.5]
INTEREST_NUM_PER_CATEGORY = 3
NEW_MOVIE_NUM = 20
RECOMMEND_NUM = 6

class UserInterest:
    def __init__(self):
        self.dic_dir = 'process_url/dic'
        self.movie_dic_name = 'movie.txt'
        self.director_dic_name = 'director.txt'
        self.actor_dic_name = 'actor.txt'

        self.user_last_access = {}
        self.name_dic = [{} for _ in range(DOMAIN_NUM - 1)]
        self.id_dic = [{} for _ in range(DOMAIN_NUM - 1)]
        self.get_dic()

        self.new_movie_list = self.get_new_movie_list()
        self.load_jieba_dic()
###为结巴分词扩充词库
    def load_jieba_dic(self):
        jieba.load_userdict(os.path.join(self.dic_dir, self.movie_dic_name))
        jieba.load_userdict(os.path.join(self.dic_dir, self.director_dic_name))
        jieba.load_userdict(os.path.join(self.dic_dir, self.actor_dic_name))

    def get_new_movie_list(self):
        new_movie_list = {}
        new_movies = DoubanMovieNewest.limit(20, offset=0).select().execute().fetchall()
        for new_movie in new_movies:
            movie = DoubanMovie.where(id=new_movie.movie_id).select().execute().fetchone()
            movie_dic = {}
            #movie_dic['name'] = movie.title.encode('latin1', 'ignore').replace(' ', '').replace('·', '')
            movie_dic['movie'] = [movie.id]
            movie_dic['director'] = [long(director_id) for director_id in movie.directors.split(',') if director_id and len(director_id) == 8]
            movie_dic['actor'] = [long(cast_id) for cast_id in movie.casts.split(',') if cast_id and len(cast_id) == 8]
            movie_dic['genre'] = [long(genre_id) for genre_id in movie.genres.split(',') if genre_id and len(genre_id) == 8]
            new_movie_list[movie.id] = movie_dic
        return new_movie_list
###读入三个词典
    def get_dic(self):
        movies = DoubanMovie.select().execute().fetchall()
        directors = DoubanDirector.select().execute().fetchall()
        actors = DoubanCast.select().execute().fetchall()
        genres = DoubanGenre.select().execute().fetchall()

        fw1 = open(os.path.join(self.dic_dir, self.movie_dic_name), 'w')
        fw2 = open(os.path.join(self.dic_dir, self.director_dic_name), 'w')
        fw3 = open(os.path.join(self.dic_dir, self.actor_dic_name), 'w')
        for movie in movies:
            movie_dic = {}
            movie_name = movie.title.encode('latin1', 'ignore').replace(' ', '').replace('·', '')
            fw1.write(movie_name + ' 1' + '\n')

            movie_dic['id'] = movie.id
            movie_dic['doubanid'] = movie.doubanid
            if movie.doubanid and movie.image:
                movie_dic['director'] = movie.directors.split(',')
                movie_dic['actor'] = movie.casts.split(',')
                movie_dic['genre'] = movie.genres.split(',')
                movie_dic['domain'] = MOVIE_DOMAIN
                self.name_dic[MOVIE_DOMAIN][movie_name] = movie_dic
                self.id_dic[MOVIE_DOMAIN][str(movie.doubanid)] = movie_name

        for director in directors:
            director_dic = {}
            director_name = director.name.encode('latin1').replace(' ', '').replace('·', '')
            fw2.write(director_name + ' 1' + '\n')

            director_dic['id'] = director.id
            director_dic['doubanid'] = director.doubanid
            if director.doubanid and director.avatars:
                director_dic['domain'] = DIRECTOR_DOMAIN
                self.name_dic[DIRECTOR_DOMAIN][director_name] = director_dic
                self.id_dic[DIRECTOR_DOMAIN][str(director.doubanid)] = director_name

        for actor in actors:
            actor_dic = {}
            actor_name = actor.name.encode('latin1').replace(' ', '').replace('·',  '')
            fw3.write(actor_name + ' 1' + '\n')

            actor_dic['id'] = actor.id
            actor_dic['doubanid'] = actor.doubanid
            if actor.doubanid and actor.avatars:
                actor_dic['domain'] = ACTOR_DOMAIN
                self.name_dic[ACTOR_DOMAIN][actor_name] = actor_dic
                self.id_dic[ACTOR_DOMAIN][str(actor.doubanid)] = actor_name

        fw1.close()
        fw2.close()
        fw3.close()
###检测系统的输入
    def process_input(self):
        http_data = {}
        while 1:
            line = sys.stdin.readline()
            line = line.strip()
            if line.startswith('SourceIP:'):
                tmp = line.split(':')
                http_data['user_ip'] = tmp[1].strip()
            if line.startswith('User-Agent:'):
                tmp = line.split(':')
                http_data['user_ua'] = tmp[1].strip()
            if line.startswith('Host:'):
                tmp = line.split(':')
                http_data['host'] = tmp[1].strip()
            if line.startswith('GET '):
                tmp = line.split(' ')
                http_data['path'] = tmp[1].strip()
            if line.startswith('::'):
                if self.http_data_is_complete(http_data):
                    thread.start_new_thread(self.process_http_data, (http_data,))
                http_data = {}
###是否是新用户，如果不是，则建立新用户
    def get_user_id(self, user_ip, user_ua):
        sql_query = DoubanUser.where(user_ip=user_ip, user_ua=user_ua).select(DoubanUser.user_id)
        try:
            user = sql_query.execute().fetchone()
            if user:
                user_id = user.user_id
            else:
                user_id = self.insert_user_into_db(user_ip, user_ua)
            return user_id
        except Exception, e:
            return 0
###将新用户插入数据库
    def insert_user_into_db(self, user_ip, user_ua):
        try:
            sql_query = DoubanUser.insert(user_ip=user_ip, user_ua=user_ua)
            user_id = sql_query.execute()
            print 'add user (id: %s, ip: %s)' % (user_id, user_ip)
            return user_id
        except Exception, e:
            return 0
###
    def insert_data_into_db(self, data, user_id):
        if user_id:
            last_access_url = self.user_last_access.get(user_id)
            current_url = data['host'] + data['path']
            if current_url == last_access_url:
                return
            self.user_last_access[user_id] = data['host'] + data['path']
            #try:
            #result = DoubanUserAccessUrl.create(user_id=user_id, host=data['host'], path=data['path'])
            self.process_url(user_id, data['host'], data['path'])
                #print 'add access url (user_id: %s, host: %s, url: %s)' % (user_id, data['host'], data['path'])
            #except Exception, e:
            #    pass
###key是什么物理意义？
    def http_data_is_complete(self,http_data):
        for key in ['user_ip', 'user_ua', 'host', 'path']:
            if key not in http_data:
                return 0
        return 1
###处理网络访问数据
    def process_http_data(self, data):
        user_id = self.get_user_id(data['user_ip'], data['user_ua'])
        self.insert_data_into_db(data, user_id)
###处理url
    def process_url(self, user_id, host, path):
        change_happen = False
        if host == "www.baidu.com":
            result = re.search(r'wd=(.*?)&?$', path)
            if result:
                key_word = result.groups()[0]
                key_word = urllib.unquote(key_word).replace('·',  '')
                seg_list = jieba.cut(key_word, cut_all=True)
                for seg in seg_list:
                    seg = seg.encode('utf8')
                    for category_name_dic in self.name_dic:
                        if seg in category_name_dic:
                            change_happen = True
                            category_id = category_name_dic[seg]['id']
                            domain_id = category_name_dic[seg]['domain']
                            DoubanUserAction.create(user_id=user_id, action_type=SEARCH_ACTION, domain_id=domain_id, category_id=category_id, time=int(time.time()))
                            if domain_id == MOVIE_DOMAIN:
                                movie = category_name_dic[seg]
                                for director in movie['director']:
                                    if director:
                                        DoubanUserAction.create(user_id=user_id, action_type=RELATE_ACTION, domain_id=DIRECTOR_DOMAIN, category_id=int(director), time=int(time.time()))
                                for actor in movie['actor']:
                                    if actor:
                                        DoubanUserAction.create(user_id=user_id, action_type=RELATE_ACTION, domain_id=ACTOR_DOMAIN, category_id=int(actor), time=int(time.time()))
                                for genre in movie['genre']:
                                    if genre:
                                        DoubanUserAction.create(user_id=user_id, action_type=RELATE_ACTION, domain_id=GENRE_DOMAIN, category_id=int(genre), time=int(time.time()))

        elif host == 'movie.douban.com':
            result = re.search(r'/(\d{5,10})', path)
            if result:
                id = result.groups()[0]
                for i in range(len(self.id_dic)):
                    category_id_dic = self.id_dic[i]
                    if id in category_id_dic:
                        change_happen = True
                        domain_id = self.name_dic[i][category_id_dic[id]]['domain']
                        category_id = self.name_dic[i][category_id_dic[id]]['id']
                        DoubanUserAction.create(user_id=user_id, action_type=ACCESS_ACTION, domain_id=domain_id, category_id=category_id, time=int(time.time()))
                        if domain_id == 0:
                            movie = self.name_dic[i][category_id_dic[id]]
                            for director in movie['director']:
                                if director:
                                    DoubanUserAction.create(user_id=user_id, action_type=RELATE_ACTION, domain_id=DIRECTOR_DOMAIN, category_id=int(director), time=int(time.time()))
                            for actor in movie['actor']:
                                if actor:
                                    DoubanUserAction.create(user_id=user_id, action_type=RELATE_ACTION, domain_id=ACTOR_DOMAIN, category_id=int(actor), time=int(time.time()))
                            for genre in movie['genre']:
                                if genre:
                                    DoubanUserAction.create(user_id=user_id, action_type=RELATE_ACTION, domain_id=GENRE_DOMAIN, category_id=int(genre), time=int(time.time()))

        if change_happen:
            self.rank_user_interest(user_id)

    def run(self):
        self.process_input()
###计算用户兴趣指数并生成用户兴趣字典
    def rank_user_interest(self, user_id):
        ##建立Interest字典
        user_interest = [{} for _ in range(DOMAIN_NUM)]
        ##得到user的访问记录
        access_historys = DoubanUserAction.where(user_id=user_id).select().execute().fetchall()
        ###遍历每一条访问数据
        for ah in access_historys:
            ##获取访问数据里面的具体ID
            id = ah.category_id
            ##得到访问的数据类型ID
            domain_id =kj ah.domain_id
            ##如果ID第一次出现，则置兴趣指数为0
            if id not in user_interest[domain_id]:
                user_interest[domain_id][id] = 0
            ##根据用户行为类型计算兴趣指数
            user_interest[domain_id][id] += ACTION_TYPE_TO_DEGREE[ah.action_type]

        self.insert_interest_into_db(user_id, user_interest)

        self.rank_user_recommend(user_id, user_interest)
###插入douban_user_interests
    def insert_interest_into_db(self, user_id, interests):
        for i in range(DOMAIN_NUM):
            if interests[i]:
                interest = sorted(interests[i].iteritems(), key=lambda x:x[1], reverse=True)
                interest = interest[:INTEREST_NUM_PER_CATEGORY] if len(interest) >= INTEREST_NUM_PER_CATEGORY else interest
                for j in range(len(interest)):
                    result = DoubanUserInterest.where(user_id=user_id, domain_id=i, rank=j).select().execute().fetchone()
                    if result:
                        DoubanUserInterest.at(result.interest_id).update(category_id=interest[j][0]).execute()
                    else:
                        DoubanUserInterest.create(user_id=user_id, domain_id=i, rank=j, category_id=interest[j][0])
###推荐算法
   def rank_user_recommend(self, user_id, interests):
        user_recommend = {}
        ##推荐指数数组，与newMovie的数量相同，初始值为0
        for movie_id in self.new_movie_list:
            user_recommend[movie_id] = 0
        ###遍历四种数据类型
        for i in range(DOMAIN_NUM):
            sum = 0
            ##获取interest字典里数据类型对应的value数组
            if interests[i]:
                ##求value的和sum
                for key, value in interests[i].items():
                    sum += value
                ##遍历newMovies
                for movie_id in self.new_movie_list:
                    new_movie = self.new_movie_list[movie_id]
                    ##检测每个具体ID在字典里的Value，如果出现在兴趣字典里，则进行加权
                    ##加权方法为  权值=【（某具体ID的兴趣值）/（该具体ID所在数据类型的所有具体ID的兴趣值之和）】
                    for key in ['movie', 'director', 'actor', 'genre']:
                        for category_id in new_movie[key]:
                            if category_id in interests[i]:
                                user_recommend[movie_id] +=. interests[i][category_id] / sum * 100
        ###排序
        recommend = sorted(user_recommend.iteritems(), key=lambda x:x[1], reverse=True)
        ###显示前6位
        for i in range(RECOMMEND_NUM):
            result = DoubanUserRecommend.where(user_id=user_id, rank=i).select().execute().fetchone()
            if result:
                DoubanUserRecommend.at(result.recommend_id).update(movie_id=recommend[i][0]).execute()
            else:
                DoubanUserRecommend.create(user_id=user_id, movie_id=recommend[i][0], rank=i)

if __name__ == "__main__":
    ui = UserInterest()
    ui.run()
