# -*- coding: UTF-8 -*-
# Set Language
LANG='JA' # JA or EN
# Uncomment the following line to force service_code='digital'
# service_code = 'digital'
# Uncomment the following line to force service_code='mono'
# service_code = 'mono' 

# Uncomment to enable logging (lol)
#import py_common.log as log
import sys, json, re
import psycopg2
conn = psycopg2.connect(database="r18",
                        host="localhost",
                        user="alpha",
                        password="postgres",
                        port="5432")

def get_content_id(dvd_code, service_code='%'):
    cursor = conn.cursor()
    cursor.execute(f"""
                   SELECT dvd_id, content_id, service_code
                   FROM public.derived_video 
                   WHERE dvd_id='{dvd_code}' AND service_code like '{service_code}'
                   ORDER BY dvd_id ASC, service_code ASC
                   """)
    result = cursor.fetchall()
    cursor.close()

    return result # tuples:(dvd_id, content_id, service_code)

def get_scene_info(content_id, service_code='%'):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT title_ja, title_en, MT.target_en, comment_ja, comment_en, release_date, jacket_full_url, maker_id, series_id, dvd_id, service_code
                    FROM derived_video 
                    LEFT JOIN machine_translation MT ON derived_video.title_ja = MT.source_ja
                    WHERE content_id='{content_id}' AND service_code like '{service_code}' 
                    ORDER BY dvd_id ASC, service_code ASC
                   """)
    result = cursor.fetchone()
    # When multiple content_id, will return in this priority: digital, e-books, mono, rental
    cursor.close()

    return result

def get_actress_info(content_id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT A.name_kanji, A.name_romaji, MT.target_en
                    FROM public.derived_video_actress VA
                    LEFT JOIN public.derived_actress A ON VA.actress_id=A.id
                    LEFT JOIN machine_translation MT ON A.name_kanji = MT.source_ja
                    WHERE VA.content_id = '{content_id}'
                    ORDER BY ordinality ASC
                   """)
    result = cursor.fetchall()
    cursor.close()

    return result

def get_director_info(content_id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT D.name_kanji, D.name_romaji, MT.target_en
                    FROM public.derived_video_director VD
                    LEFT JOIN public.derived_director D ON VD.director_id=D.id
                    LEFT JOIN machine_translation MT ON D.name_kanji = MT.source_ja
                    WHERE VD.content_id = '{content_id}'
                   """)
    result = cursor.fetchall()
    cursor.close()

    return result

def get_tags(content_id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT C.name_ja , C.name_en, MT.target_en
                    FROM public.derived_video_category VC
                    LEFT JOIN public.derived_category C ON VC.category_id=C.id
                    LEFT JOIN machine_translation MT ON C.name_ja = MT.source_ja
                    WHERE VC.content_id = '{content_id}' 
                   """)
    result = cursor.fetchall()
    cursor.close()

    return result

def get_studio(maker_id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT M.name_ja, M.name_en, MT.target_en FROM public.derived_maker M
                    LEFT JOIN machine_translation MT ON M.name_ja = MT.source_ja
                    WHERE M.id = '{maker_id}'
                   """)
    result = cursor.fetchone()
    cursor.close()

    return result

def get_series(series_id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT S.name_ja, S.name_en, MT.target_en FROM public.derived_series S
                    LEFT JOIN machine_translation MT ON S.name_ja = MT.source_ja
                    WHERE S.id = '{series_id}'
                   """)
    result = cursor.fetchone()
    cursor.close()

    return result

SUPER_DUPER_JAV_CODE_REGEX = r'.*?([a-zA-Z|tT28|tT38]+)-?(\d+)[zZ]?[eE]?(?:-pt)?(\d{1,2})?.*'

i = json.loads(sys.stdin.read())

dvd_code_found = False
content_id_found = False
if (sys.argv[1] == "sceneByName"):
    query_string = i['name']
    if(re.search(SUPER_DUPER_JAV_CODE_REGEX,query_string)):
        dvd_code = re.search(SUPER_DUPER_JAV_CODE_REGEX,query_string).group(1)+'-'+re.search(SUPER_DUPER_JAV_CODE_REGEX,query_string).group(2)
        dvd_code_found = True
elif (sys.argv[1] == "sceneByQueryFragment" or sys.argv[1] == "sceneByFragment"):
    try:
        input_title = i['title']
        print(input_title, file=sys.stderr)
        if(re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title)):
            print("XXXXXXXX", file=sys.stderr)
            dvd_code = re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title).group(1)+'-'+re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title).group(2)
            dvd_code_found = True
    except:
        pass
    try:
        input_code = i['code']
        if(re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title)):
            dvd_code = re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title).group(1)+'-'+re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title).group(2)
            dvd_code_found = True
    except:
        pass
    try:
        input_url = i['url']
        if(re.search(r'.*id=(.*)/.*',input_url)):
            content_id = re.search(r'.*id=(.*)/.*',input_url).group(1)
            content_id_found = True
    except:
        pass
elif (sys.argv[1] == "sceneByURL"):
    input_url = i['url']
    if(re.search(r'.*id=(.*)/.*',input_url)):
        content_id = re.search(r'.*id=(.*)/.*',input_url).group(1)
        content_id_found = True

if(content_id_found == False):
    content_ids = get_content_id(dvd_code)
    content_id = content_ids[0][1]

scene_info = get_scene_info(content_id)

title_ja = scene_info[0]
title_en = scene_info[2] if scene_info[1] is None else scene_info[1]
details_ja = scene_info[3]
details_en = scene_info[4]
date = scene_info[5].strftime("%Y-%m-%d")
url = "https://r18.dev/videos/vod/movies/detail/-/id="+content_id+"/"
service_code = scene_info[10]
if service_code == "digital":
    image = "https://awsimgsrc.dmm.com/dig/"+scene_info[6]+".jpg"
else: # assume mono
    image = "https://awsimgsrc.dmm.com/dig/"+scene_info[6].replace('adult/','')+".jpg"
    # Old DMM endpoint
    #image = "https://pics.dmm.co.jp/"+scene_info[6]+".jpg"
maker_id = scene_info[7]
series_id = scene_info[8]
code = scene_info[9]
    
actress_info = get_actress_info(content_id)
actress_ja = [{'name': i[0]} for i in actress_info]
actress_en = [{'name': i[2]} if i[1] is None else {'name': i[1]} for i in actress_info]
# If actress_en is still None, return the Japanese name - hope you have aliases set up locally
actress_en = [{'name': i['name']} if j['name'] is None else {'name': j['name']} for i,j in zip(actress_ja,actress_en)]

director_info = get_director_info(content_id)
director_ja = [i[0] for i in director_info]
director_en = [i[2] if i[1] is None else i[1] for i in director_info]
director_en = [i if j is None else j for i,j in zip(director_ja,director_en)]

director_ja = ', '.join(director_ja)
director_en = ', '.join(director_en)

tags_info = get_tags(content_id)
tags_ja = [i[0] for i in tags_info]
tags_en = [i[2] if i[1] is None else i[1] for i in tags_info]
tags_en = [i if j is None else j for i,j in zip(tags_ja,tags_en)]

studio_info = get_studio(maker_id)
studio_ja = {'name': studio_info[0]}
studio_en = {'name': studio_info[2]} if studio_info[1] is None else {'name': studio_info[1]}
studio_en = {'name': studio_info[0]} if studio_en['name'] is None else studio_en

if series_id is None:
    series_ja = ""
    series_en = ""
else:
    series_info = get_series(series_id)
    series_ja = series_info[0]
    series_en = series_info[2] if series_info[1] is None else series_info[1]
    series_en = series_info[0] if series_en is None else series_en

res = {}

res["date"] = date
res["url"] = url
res["image"] = image
res["code"] = code

if (LANG == 'JA'):
    if title_ja is not None:
        res["title"] = title_ja
    if details_ja is not None:
        res["details"] = details_ja
    if actress_ja is not None:
        res["performers"] = actress_ja
    if director_ja is not None:
        res["director"] = director_ja
    if studio_ja is not None:
        res["studio"] = studio_ja
    if title_ja is not None:
        res["movie"] = title_ja
elif (LANG == 'EN'):
    if title_en is not None:
        res["title"] = title_en
    if details_en is not None:
        res["details"] = details_en
    if actress_en is not None:
        res["performers"] = actress_en
    if director_en is not None:
        res["director"] = director_en
    if studio_en is not None:
        res["studio"] = studio_en
    if title_en is not None:
        res["movie"] = title_en

print(json.dumps(res))
conn.close()

