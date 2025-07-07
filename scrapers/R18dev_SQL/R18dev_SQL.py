# -*- coding: UTF-8 -*-
import sys, json, re, csv
import psycopg2
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def log(*s):
    print(*s, file=sys.stderr)

try:
    import psycopg2
except ModuleNotFoundError:
    log("ERROR | psycopg2 not found, try pip install psycopg2-binary")
    sys.exit(1)

if(sys.platform=='win32'):
    ensure_ascii=True
else:
    ensure_ascii=False

# Set Language
LANG='JA' # JA or EN

# StashDB Submission Mode 
stashdb_mode = False

service_code = '%'
# Uncomment the following line to force service_code='digital'
# service_code = 'digital'
# Uncomment the following line to force service_code='mono'
# service_code = 'mono' 

# If True, uses label instead of maker for studio (eg: Moodyz Acid instead of Moodyz)
use_label_as_studio = False

conn = psycopg2.connect(database="r18",
                        host="localhost",
                        user="postgres",
                        password="postgres",
                        port="5432")

def get_content_id(dvd_code, service_code='%'):
    cursor = conn.cursor()
    cursor.execute(f"""
                   SELECT dvd_id, content_id, service_code
                   FROM public.derived_video 
                   WHERE UPPER(dvd_id)='{dvd_code}' AND service_code like '{service_code}'
                   ORDER BY dvd_id ASC, service_code ASC
                   """)
    result = cursor.fetchall()
    cursor.close()

    return result # tuples:(dvd_id, content_id, service_code)

def get_scene_info(content_id, service_code='%'):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT title_ja, title_en, MT.target_en, comment_ja, comment_en, release_date, jacket_full_url, maker_id, label_id, series_id, dvd_id, service_code
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
                    SELECT A.name_kanji, A.name_romaji, MT.target_en, A.id
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
                    SELECT M.name_ja, M.name_en, MT.target_en
                    FROM public.derived_maker M
                    LEFT JOIN machine_translation MT ON M.name_ja = MT.source_ja
                    WHERE M.id = '{maker_id}'
                   """)
    result = cursor.fetchone()
    cursor.close()

    return result

def get_label(label_id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT L.name_ja, L.name_en, MT.target_en
                    FROM public.derived_label L
                    LEFT JOIN machine_translation MT ON L.name_ja = MT.source_ja
                    WHERE L.id = '{label_id}'
                   """)
    result = cursor.fetchone()
    cursor.close()

    return result

def get_series(series_id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT S.name_ja, S.name_en, MT.target_en
                    FROM public.derived_series S
                    LEFT JOIN machine_translation MT ON S.name_ja = MT.source_ja
                    WHERE S.id = '{series_id}'
                   """)
    result = cursor.fetchone()
    cursor.close()

    return result

def find_performer_by_name(name):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT id, name_kanji, name_romaji
                    FROM derived_actress 
                    WHERE name_kanji = '{name}' or name_romaji = '{name}'
                    ORDER BY id ASC
                   """)
    result = cursor.fetchall()
    cursor.close()
    return result

def find_performer_by_id(id):
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT id, name_kanji, name_romaji
                    FROM derived_actress 
                    WHERE id = {id}
                    ORDER BY id ASC
                   """)
    result = cursor.fetchone()
    cursor.close()
    return result

def searchPerformer(name):
    ret = []
    results = find_performer_by_name(i['name'])
    for result in results:
        p = {}
        p['name'] = result[1] + "\t" + ("" if result[2] is None else result[2]) + "\t (" + str(result[0]) + ")"
        p['url'] = str(result[0])
        log("search:",p['url'])
        ret.append(p)
    return ret

def scrapePerformer(input):
    ret = {}
    actressid = str(input['url'])
    log(actressid)
    result = find_performer_by_id(actressid)
    if (LANG == "JA"):
        ret['name'] = result[1]
        ret['aliases'] = "" if result[2] is None else result[2]
    else:
        ret['name'] = result[1] if result[2] is None else result[2]
        ret['aliases'] = result[1]

    ret['urls'] = ["https://actress.dmm.co.jp/-/detail/=/actress_id="+actressid+"/","https://r18.dev/videos/vod/movies/list/?id="+actressid+"&type=actress"]
    return ret

def decensor(string):
    if string is None:
        return None
    with open('decensor.csv', 'r') as decensor_file:
        decensor_reader = csv.reader(decensor_file)
        for row_decensor in decensor_reader:
            string = string.replace(row_decensor[0],row_decensor[1])
    return string

def readJSONInput():
    input = sys.stdin.read()
    return json.loads(input)

SUPER_DUPER_JAV_CODE_REGEX = r'.*?([A-Z]+|[3DSVR]+|[T28]+|[T38]+)-?(\d+[Z]?[E]?)(?:-pt)?(\d{1,2})?.*' # https://regex101.com/r/K6RizW/1

i = readJSONInput()
log(json.dumps(i, ensure_ascii=ensure_ascii), "@", sys.argv[1])

dvd_code_found = False

if (sys.argv[1] == "performerByName"):
    ret = searchPerformer(i['name'])
    print(json.dumps(ret))
    sys.exit(0)

elif (sys.argv[1] == "performerByFragment"):
    ret = scrapePerformer(i)
    print(json.dumps(ret))
    sys.exit(0)

elif (sys.argv[1] == "sceneByName"):
    query_string = i['name']
    if(re.search(SUPER_DUPER_JAV_CODE_REGEX,query_string, flags=re.IGNORECASE)):
        dvd_code = re.search(SUPER_DUPER_JAV_CODE_REGEX,query_string, flags=re.IGNORECASE).group(1)+'-'+re.search(SUPER_DUPER_JAV_CODE_REGEX,query_string, flags=re.IGNORECASE).group(2)
        dvd_code_found = True
        log(sys.argv[1],"| DVD CODE: "+dvd_code)        
    else:
        content_id = query_string
        log(sys.argv[1],"| DVD CODE NOT FOUND")
        log(sys.argv[1],"| TRY CONTENT ID: "+content_id)

elif (sys.argv[1] == "sceneByQueryFragment" or sys.argv[1] == "sceneByFragment"):
    flag = False
    try:
        for j in i['urls']:
            input_url = j
            if (flag):
                pass
            elif(re.search(r'.*r18\.dev.*id=(\w*)\/?',input_url)):
                content_id = re.search(r'.*r18\.dev.*id=(\w*)\/?',input_url).group(1)
                log(sys.argv[1],"| URL | CONTENT ID: "+content_id + "|" + input_url)
                flag = True
            elif(re.search(r'.*dmm.*mono.*cid=(\w*)\/?',input_url)):
                content_id = re.search(r'.*dmm.*mono.*cid=(\w*)\/?',input_url).group(1)
                service_code = "mono"
                log(sys.argv[1],"| URL | CONTENT ID: "+content_id+ "|" + input_url)
                flag = True
            elif(re.search(r'.*dmm.*videoa.*cid=(\w*)\/?',input_url)):
                content_id = re.search(r'.*dmm.*videoa.*cid=(\w*)\/?',input_url).group(1)
                service_code = "digital"
                log(sys.argv[1],"| URL | CONTENT ID: "+content_id+ "|" + input_url)
                flag = True
    except:
        pass
    try:
        if(flag == False):
            input_code = i['code']
            if(re.search(SUPER_DUPER_JAV_CODE_REGEX,input_code, flags=re.IGNORECASE)):
                dvd_code = re.search(SUPER_DUPER_JAV_CODE_REGEX,input_code, flags=re.IGNORECASE).group(1)+'-'+re.search(SUPER_DUPER_JAV_CODE_REGEX,input_code, flags=re.IGNORECASE).group(2)
                log(sys.argv[1],"| CODE | DVD CODE: "+dvd_code)
                flag = True
                dvd_code_found = True
    except:
        pass
    try:
        if(flag == False):
            input_title = i['title']
            if(re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title, flags=re.IGNORECASE)):
                dvd_code = re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title, flags=re.IGNORECASE).group(1)+'-'+re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title, flags=re.IGNORECASE).group(2)
                log(sys.argv[1],"| TITLE | DVD CODE: "+dvd_code)
                dvd_code_found = True
        else:
            pass
    except:
        pass

elif (sys.argv[1] == "sceneByURL"):
    input_url = i['url']
    if(re.search(r'.*r18\.dev.*id=(\w*)\/?',input_url)):
        content_id = re.search(r'.*r18\.dev.*id=(\w*)\/?',input_url).group(1)
        log(sys.argv[1],"| URL | CONTENT ID: "+content_id + "|" + input_url)
        flag = True
    elif(re.search(r'.*dmm.*mono.*cid=(\w*)\/?',input_url)):
        content_id = re.search(r'.*dmm.*mono.*cid=(\w*)\/?',input_url).group(1)
        service_code = "mono"
        log(sys.argv[1],"| URL | CONTENT ID: "+content_id+ "|" + input_url)
        flag = True
    elif(re.search(r'.*dmm.*videoa.*cid=(\w*)\/?',input_url)):
        content_id = re.search(r'.*dmm.*videoa.*cid=(\w*)\/?',input_url).group(1)
        service_code = "digital"
        log(sys.argv[1],"| URL | CONTENT ID: "+content_id+ "|" + input_url)
        flag = True

if(dvd_code_found):
    try:
        content_ids = get_content_id(dvd_code.upper(), service_code)
        content_id = content_ids[0][1]
        log("DVD CODE:", dvd_code," -> ",content_ids[0][1],"@",content_ids[0][2])
    except:
        log("Cannot find a corresponding content_id for dvd_code:", dvd_code)
        content_id = dvd_code.replace('-','')
        log("Fallback to :", content_id)

content_id = content_id.lower()
scene_info = get_scene_info(content_id, service_code)
log("CONTENT ID:", content_id,"@",service_code)

title_ja = scene_info[0]
title_en = decensor(scene_info[2]) if scene_info[1] is None else decensor(scene_info[1])
details_ja = scene_info[3]
details_en = decensor(scene_info[4])
date = scene_info[5].strftime("%Y-%m-%d")
urls = ["https://r18.dev/videos/vod/movies/detail/-/id="+content_id+"/"]
service_code = scene_info[11]
if service_code == "digital":
    image = "https://awsimgsrc.dmm.com/dig/"+scene_info[6]+".jpg"
    urls.append("https://www.dmm.co.jp/digital/videoa/-/detail/=/cid="+content_id+"/")
elif service_code == "mono": # assume mono
    image = "https://awsimgsrc.dmm.com/dig/"+scene_info[6].replace('adult/','')+".jpg"
    urls.append("http://www.dmm.co.jp/mono/dvd/-/detail/=/cid="+content_id+"/")
else:
    image = "https://pics.dmm.co.jp/"+scene_info[6]+".jpg"

maker_id = scene_info[7]
label_id = scene_info[8]
series_id = scene_info[9]
code = scene_info[10]
    
actress_info = get_actress_info(content_id)
actress_ja = [{'name': i[0], 'urls': ['https://r18.dev/videos/vod/movies/list/?id='+str(i[3])+'&type=actress']} for i in actress_info]
actress_en = [{'name': i[2], 'urls': ['https://r18.dev/videos/vod/movies/list/?id='+str(i[3])+'&type=actress']} if i[1] is None else {'name': i[1], 'url': 'https://r18.dev/videos/vod/movies/list/?id='+str(i[3])+'&type=actress'} for i in actress_info]
# If actress_en is still None, return the Japanese name - hope you have aliases set up locally
actress_en = [i if j['name'] is None else j for i,j in zip(actress_ja,actress_en)]

director_info = get_director_info(content_id)
director_ja = [i[0] for i in director_info]
director_en = [i[2] if i[1] is None else i[1] for i in director_info]
director_en = [i if j is None else j for i,j in zip(director_ja,director_en)]

director_ja = ', '.join(director_ja)
director_en = ', '.join(director_en)

tags_info = get_tags(content_id)
tags_ja = [{'name': i[0]} for i in tags_info]
tags_en = [{'name': decensor(i[2])} if i[1] is None else {'name': decensor(i[1])} for i in tags_info]
tags_en = [{'name': i['name']} if j['name'] is None else {'name': j['name']} for i,j in zip(tags_ja,tags_en)]

studio_info = get_studio(maker_id)
studio_ja = {'name': studio_info[0]}
studio_en = {'name': studio_info[2]} if studio_info[1] is None else {'name': studio_info[1]}
studio_en = {'name': studio_info[0]} if studio_en['name'] is None else studio_en

studio_ja['url'] = "https://r18.dev/videos/vod/movies/list/?id="+str(maker_id)+"&type=studio"
studio_en['url'] = "https://r18.dev/videos/vod/movies/list/?id="+str(maker_id)+"&type=studio"

if(label_id is None):
    label_ja = None
    label_en = None
else:
    label_info = get_label(label_id)
    label_ja = {'name': label_info[0]}
    label_en = {'name': decensor(label_info[2])} if label_info[1] is None else {'name': decensor(label_info[1])}
    label_en = {'name': label_info[0]} if label_en['name'] is None else label_en
    label_ja['url'] = "https://r18.dev/videos/vod/movies/list/?id="+str(label_id)+"&type=label"
    label_en['url'] = "https://r18.dev/videos/vod/movies/list/?id="+str(label_id)+"&type=label"


if (series_id is None):
    series_ja = None
    series_en = None
else:
    series_info = get_series(series_id)
    series_ja = {'name': series_info[0]}
    series_en = {'name': decensor(series_info[2])} if series_info[1] is None else {'name': decensor(series_info[1])}
    series_en = {'name': series_info[0]} if series_en['name'] is None else series_en
    series_ja['urls'] = ["https://r18.dev/videos/vod/movies/list/?id="+str(series_id)+"&type=series"]
    series_en['urls'] = ["https://r18.dev/videos/vod/movies/list/?id="+str(series_id)+"&type=series"]

res = {}

res["date"] = date
res["urls"] = urls
res["image"] = image
res["code"] = code

if (LANG == 'EN' or stashdb_mode):
    if stashdb_mode:
        res["title"] = code
        if title_en is not None:
            res["details"] = title_en
        if details_en is not None:
            res["details"] += '\n\n'+details_en
    else:
        if title_en is not None:
            res["title"] = title_en
        if details_en is not None:
            res["details"] = details_en
    if actress_en is not None:
        res["performers"] = actress_en
    if director_en is not None:
        res["director"] = director_en
    if tags_en is not None:
        res["tags"] = tags_en
    if (use_label_as_studio or stashdb_mode) and label_en is not None:
        res["studio"] = label_en
    else:
        if studio_en is not None:
            res["studio"] = studio_en
    if series_en is not None:
        res["groups"] = [series_en]
elif (LANG == 'JA'):
    if title_ja is not None:
        res["title"] = title_ja
    if details_ja is not None:
        res["details"] = details_ja
    if actress_ja is not None:
        res["performers"] = actress_ja
    if director_ja is not None:
        res["director"] = director_ja
    if tags_ja is not None:
        res["tags"] = tags_ja
    if use_label_as_studio and label_ja is not None:
        res["studio"] = label_ja
    else:
        if studio_ja is not None:
            res["studio"] = studio_ja
    if series_ja is not None:
        res["groups"] = [series_ja]


conn.close()
log(res["performers"])
if (sys.argv[1] == "sceneByName"):
    print(json.dumps([res],ensure_ascii=ensure_ascii)) 
else:
    print(json.dumps(res,ensure_ascii=ensure_ascii)) 
