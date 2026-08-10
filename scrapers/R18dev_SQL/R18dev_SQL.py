import os
# -*- coding: UTF-8 -*-
import sys, json, re, csv
import requests
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def log(*s):
    print(*s, file=sys.stderr)

try:
    import psycopg2
except ModuleNotFoundError:
    log("ERROR | psycopg2 not found, try pip install psycopg2-binary")
    sys.exit(1)

BOGUS_PREFIXES = {
    'MP', 'MKV', 'AVI', 'WMV', 'FLV', 'MOV', 'TS', 'PART', 'PT', 'VOL', 'EP', 'E',
    'VIDEO', 'VIDEOS', 'CLIP', 'CLIPS', 'SCENE', 'SCENES', 'FULL', 'ONLYFANS',
    'VERTICAL', 'HORIZONTAL', 'SHORT', 'SHORTS', 'UNCENSORED', 'CENSORED',
    'DISC', 'CD', 'DVD', 'BD', 'BLURAY', 'REPACK', 'PROPER', 'WEB', 'DL', 'WEBDL', 'JAPANHDV'
}

# Regex pattern for standard JAV DVD codes (handles BBAN-594, C-2963, 2CHCH-030, etc.)
SUPER_DUPER_JAV_CODE_REGEX = r'.*?\b(\d*[a-zA-Z]{1,6})-?(\d+[Zz]?[Ee]?)(?:-pt)?(\d{1,2})?.*'

def clean_prefix(pref):
    if not pref:
        return ""
    # Strip leading digits added by DMM providers (e.g., 2DDHZ -> DDHZ, 11ID -> ID, 7BNSPS -> BNSPS)
    cleaned = re.sub(r'^\d+', '', pref)
    return cleaned.upper() if len(cleaned) >= 1 else pref.upper()

def is_valid_jav_code(prefix, num):
    prefix = clean_prefix(prefix)
    if prefix in BOGUS_PREFIXES:
        return False
    if not re.search(r'[A-Za-z]', prefix):
        return False
    if len(prefix) < 1 or len(prefix) > 7:
        return False
    return True

def sanitize_code(c):
    if not c or str(c).strip().lower() in ['none', 'null', '']:
        return None
    m = re.search(r'\b(\d*[a-zA-Z]{1,6})[-_]?(\d+)\b', str(c).strip())
    if m:
        pref = clean_prefix(m.group(1))
        num_str = m.group(2)
        
        # Insert dash and preserve 4-digit padding if present (e.g., GASO0014 -> GASO-0014)
        if len(num_str) >= 4 and num_str.startswith('0'):
            return f"{pref}-{num_str}"
        else:
            try:
                num_int = int(num_str)
                return f"{pref}-{num_int:03d}"
            except ValueError:
                return f"{pref}-{num_str}"
    return str(c).strip()

def extract_jav_code_from_content_id(cid):
    if not cid:
        return None
    # Strip DMM provider prefixes like h_900, h_068, 13, 2, 7, 11, etc.
    cleaned = re.sub(r'^(?:h_\d+|\d{1,4})', '', cid, flags=re.IGNORECASE)
    matches = re.findall(r'([a-zA-Z]{1,6})0*(\d{2,5})', cleaned)
    for pref, num in matches:
        if is_valid_jav_code(pref, num):
            return sanitize_code(f"{pref}{num}")
    
    matches_raw = re.findall(r'([a-zA-Z]{1,6})0*(\d{2,5})', cid)
    for pref, num in matches_raw:
        if is_valid_jav_code(pref, num):
            return sanitize_code(f"{pref}{num}")
    return None

if(sys.platform=='win32'):
    ensure_ascii=True
else:
    ensure_ascii=False

# Set Language
LANG='EN' # JA or EN

# StashDB Submission Mode
stashdb_mode = True

service_code = '%'

# If True, uses label instead of maker for studio
use_label_as_studio = False

conn = psycopg2.connect(database="r18",
                        host="postgres",
                        user="postgres",
                        password="postgres",
                        port="5432")

def get_content_id(dvd_code, service_code='%'):
    conn.rollback()
    cursor = conn.cursor()
    cursor.execute(f"""
                   SELECT dvd_id, content_id, service_code
                   FROM public.derived_video 
                   WHERE UPPER(dvd_id)='{dvd_code.upper()}' AND service_code like '{service_code}'
                   ORDER BY dvd_id ASC, service_code ASC
                   """)
    result = cursor.fetchall()

    if not result and '-' in dvd_code:
        parts = dvd_code.split('-', 1)
        if len(parts) == 2 and parts[1].isdigit():
            prefix = parts[0].upper()
            num_int = int(parts[1])
            alt_codes = [f"{prefix}-{num_int:03d}", f"{prefix}-{num_int:02d}", f"{prefix}-{num_int}"]
            for alt in alt_codes:
                cursor.execute(f"""
                               SELECT dvd_id, content_id, service_code
                               FROM public.derived_video 
                               WHERE UPPER(dvd_id)='{alt}' AND service_code like '{service_code}'
                               ORDER BY dvd_id ASC, service_code ASC
                               """)
                result = cursor.fetchall()
                if result:
                    break

    if not result and '-' in dvd_code:
        prefix, num_str = dvd_code.split('-', 1)
        digits = ''.join(filter(str.isdigit, num_str))
        if digits:
            num_int = int(digits)
            pattern = f"%{prefix.lower()}%{num_int:03d}%"
            cursor.execute(f"""
                           SELECT dvd_id, content_id, service_code
                           FROM public.derived_video 
                           WHERE content_id LIKE '{pattern}' AND service_code like '{service_code}'
                           ORDER BY dvd_id ASC, service_code ASC
                           """)
            result = cursor.fetchall()

    cursor.close()
    return result

def get_scene_info(content_id, service_code='%'):
    conn.rollback()
    cursor = conn.cursor()
    cursor.execute(f"""
                    SELECT title_ja, title_en, MT.target_en, comment_ja, comment_en, release_date, jacket_full_url, maker_id, label_id, series_id, dvd_id, service_code
                    FROM derived_video 
                    LEFT JOIN machine_translation MT ON derived_video.title_ja = MT.source_ja
                    WHERE content_id='{content_id}' AND service_code like '{service_code}' 
                    ORDER BY dvd_id ASC, service_code ASC
                   """)
    result = cursor.fetchone()
    cursor.close()
    return result

def get_actress_info(content_id):
    conn.rollback()
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
    conn.rollback()
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
    conn.rollback()
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
    conn.rollback()
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
    conn.rollback()
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
    conn.rollback()
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
    conn.rollback()
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
    conn.rollback()
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
        if(result[2] is None):
            eng = wikidata(str(result[0]))
        else:
            eng = result[2]
        p['name'] = result[1] + "\t" + ("" if eng is None else eng) + "\t (" + str(result[0]) + ")"
        p['url'] = str(result[0])
        log("search:",p['url'])
        ret.append(p)
    return ret

def scrapePerformer(input):
    ret = {}
    actressid = str(input['url'])
    log("Actress ID:", actressid)
    result = find_performer_by_id(actressid)
    if(result[2] is None):
        eng = wikidata(str(result[0]))
    else:
        eng = result[2]
    if (LANG == "JA"):
        ret['name'] = result[1]
        ret['aliases'] = "" if eng is None else eng
    else:
        ret['name'] = result[1] if eng is None else eng
        ret['aliases'] = result[1]

    ret['urls'] = ["https://actress.dmm.co.jp/-/detail/=/actress_id="+actressid+"/","https://r18.dev/videos/vod/movies/list/?id="+actressid+"&type=actress"]
    return ret

def wikidata(pid):
    wikidata_url = 'https://query.wikidata.org/sparql'
    query = f'''
    SELECT DISTINCT ?item ?itemLabel WHERE {{
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      {{
        SELECT DISTINCT ?item WHERE {{
          ?item p:P9781 ?statement0.
          ?statement0 (ps:P9781) "{pid}".
        }}
        LIMIT 3
      }}
    }}
    '''
    r = requests.get(wikidata_url, params = {'format': 'json', 'query': query})
    data = r.json()
    log(data)
    try:
        wikidata_name = data['results']['bindings'][0]['itemLabel']['value']
    except:
        wikidata_name = None
    return wikidata_name

def decensor(string):
    if string is None:
        return None
    decensor_file_path = os.path.join(os.path.dirname(__file__), 'decensor.csv')
    if os.path.exists(decensor_file_path):
        with open(decensor_file_path, 'r', encoding='utf-8') as decensor_file:
            decensor_reader = csv.reader(decensor_file)
            for row_decensor in decensor_reader:
                if len(row_decensor) >= 2:
                    string = string.replace(row_decensor[0], row_decensor[1])
    return string

def readJSONInput():
    input_data = sys.stdin.read()
    return json.loads(input_data)

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
    m = re.search(SUPER_DUPER_JAV_CODE_REGEX, query_string, flags=re.IGNORECASE)
    if m and is_valid_jav_code(m.group(1), m.group(2)):
        dvd_code = sanitize_code(f"{m.group(1)}{m.group(2)}")
        dvd_code_found = True
        log(sys.argv[1],"| DVD CODE: "+dvd_code)        
    else:
        content_id = query_string
        log(sys.argv[1],"| DVD CODE NOT FOUND/VALID | TRY CONTENT ID: "+content_id)

elif (sys.argv[1] == "sceneByQueryFragment" or sys.argv[1] == "sceneByFragment"):
    # STRICT FILENAME IMMUNIZATION CHECK
    has_jav_code = False
    if i.get('files'):
        for file_obj in i.get('files', []):
            filepath = file_obj.get('path', '')
            filename = filepath.split('/')[-1]
            m = re.search(SUPER_DUPER_JAV_CODE_REGEX, filename, flags=re.IGNORECASE)
            if m and is_valid_jav_code(m.group(1), m.group(2)):
                has_jav_code = True
                break

    if not has_jav_code:
        print("null")
        sys.exit(0)

    flag = False
    try:
        for j in i.get('urls', []):
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
            input_code = i.get('code')
            if input_code:
                m = re.search(SUPER_DUPER_JAV_CODE_REGEX,input_code, flags=re.IGNORECASE)
                if m and is_valid_jav_code(m.group(1), m.group(2)):
                    dvd_code = sanitize_code(f"{m.group(1)}{m.group(2)}")
                    log(sys.argv[1],"| CODE | DVD CODE: "+dvd_code)
                    flag = True
                    dvd_code_found = True
    except:
        pass

    try:
        if(flag == False):
            input_title = i.get('title')
            if input_title:
                m = re.search(SUPER_DUPER_JAV_CODE_REGEX,input_title, flags=re.IGNORECASE)
                if m and is_valid_jav_code(m.group(1), m.group(2)):
                    dvd_code = sanitize_code(f"{m.group(1)}{m.group(2)}")
                    log(sys.argv[1],"| TITLE | DVD CODE: "+dvd_code)
                    dvd_code_found = True
                    flag = True
    except:
        pass

    # FALLBACK: Parse code directly from filename for automated Identify scans
    try:
        if(flag == False):
            if i.get('files'):
                for file_obj in i.get('files', []):
                    filepath = file_obj.get('path', '')
                    filename = filepath.split('/')[-1]
                    m = re.search(SUPER_DUPER_JAV_CODE_REGEX, filename, flags=re.IGNORECASE)
                    if m and is_valid_jav_code(m.group(1), m.group(2)):
                        dvd_code = sanitize_code(f"{m.group(1)}{m.group(2)}")
                        log(sys.argv[1], "| FILENAME | DVD CODE: " + dvd_code)
                        dvd_code_found = True
                        flag = True
                        break
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

if not scene_info:
    print("null")
    sys.exit(0)

title_ja = scene_info[0]
title_en = decensor(scene_info[2]) if scene_info[1] is None else decensor(scene_info[1])
details_ja = scene_info[3]
details_en = decensor(scene_info[4])
date = scene_info[5].strftime("%Y-%m-%d")
urls = ["https://r18.dev/videos/vod/movies/detail/-/id="+content_id+"/"]
service_code = scene_info[11]

# Image URL formatting & 404 validation
target_image_url = None
if service_code == "digital":
    target_image_url = "https://awsimgsrc.dmm.com/dig/"+scene_info[6]+".jpg"
    urls.append("https://www.dmm.co.jp/digital/videoa/-/detail/=/cid="+content_id+"/")
elif service_code == "mono":
    target_image_url = "https://awsimgsrc.dmm.com/dig/"+scene_info[6].replace('adult/','')+".jpg"
    urls.append("https://www.dmm.co.jp/mono/dvd/-/detail/=/cid="+content_id+"/")
else:
    target_image_url = "https://pics.dmm.co.jp/"+scene_info[6]+".jpg"

# Validate image HTTP status so 404 links won't crash Stash
image = None
if target_image_url:
    try:
        r = requests.head(target_image_url, timeout=2, allow_redirects=True)
        if r.status_code == 200:
            image = target_image_url
        else:
            fallback_url = "https://pics.dmm.co.jp/"+scene_info[6]+".jpg"
            r2 = requests.head(fallback_url, timeout=2, allow_redirects=True)
            if r2.status_code == 200:
                image = fallback_url
    except Exception:
        image = target_image_url

maker_id = scene_info[7]
label_id = scene_info[8]
series_id = scene_info[9]
code = scene_info[10]

# --- RECOVER AND SANITIZE DVD CODE ---
if not code or str(code).strip().lower() in ['none', 'null']:
    if dvd_code_found and 'dvd_code' in locals() and dvd_code:
        code = dvd_code
    else:
        candidate_strings = []
        if i.get('code'): candidate_strings.append(str(i['code']))
        if i.get('title'): candidate_strings.append(str(i['title']))
        if i.get('files'):
            for file_obj in i.get('files', []):
                if file_obj.get('path'):
                    candidate_strings.append(file_obj['path'].split('/')[-1])
        
        found_code = None
        for s in candidate_strings:
            m = re.search(SUPER_DUPER_JAV_CODE_REGEX, s, flags=re.IGNORECASE)
            if m and is_valid_jav_code(m.group(1), m.group(2)):
                found_code = sanitize_code(f"{m.group(1)}{m.group(2)}")
                break
        
        if found_code:
            code = found_code
        else:
            code = extract_jav_code_from_content_id(content_id)

code = sanitize_code(code)

actress_info = get_actress_info(content_id)
actress_ja = [{'name': item[0], 'urls': ['https://r18.dev/videos/vod/movies/list/?id='+str(item[3])+'&type=actress']} for item in actress_info]
actress_en = [{'name': item[2], 'urls': ['https://r18.dev/videos/vod/movies/list/?id='+str(item[3])+'&type=actress']} if item[1] is None else {'name': item[1], 'url': 'https://r18.dev/videos/vod/movies/list/?id='+str(item[3])+'&type=actress'} for item in actress_info]
actress_en = [item if j['name'] is None else j for item,j in zip(actress_ja,actress_en)]

director_info = get_director_info(content_id)
director_ja = [item[0] for item in director_info]
director_en = [item[2] if item[1] is None else item[1] for item in director_info]
director_en = [item if j is None else j for item,j in zip(director_ja,director_en)]

director_ja = ', '.join(director_ja)
director_en = ', '.join(director_en)

tags_info = get_tags(content_id)
tags_ja = [{'name': item[0]} for item in tags_info]
tags_en = [{'name': decensor(item[2])} if item[1] is None else {'name': decensor(item[1])} for item in tags_info]
tags_en = [{'name': item['name']} if j['name'] is None else {'name': j['name']} for item,j in zip(tags_ja,tags_en)]

# Format Studio Name
studio_info = get_studio(maker_id)
if studio_info:
    raw_ja = str(studio_info[0]).strip() if studio_info[0] else None
    raw_en_val = studio_info[2] if studio_info[1] is None else studio_info[1]
    raw_en = str(raw_en_val).strip() if raw_en_val else raw_ja
    
    studio_ja = {'name': raw_ja, 'url': f"https://r18.dev/videos/vod/movies/list/?id={maker_id}&type=studio"} if raw_ja else None
    studio_en = {'name': raw_en, 'url': f"https://r18.dev/videos/vod/movies/list/?id={maker_id}&type=studio"} if raw_en else None
else:
    studio_ja = None
    studio_en = None

# Format Label Name
if label_id is None:
    label_ja = None
    label_en = None
else:
    label_info = get_label(label_id)
    if label_info:
        raw_ja = str(label_info[0]).strip() if label_info[0] else None
        raw_en_val = decensor(label_info[2]) if label_info[1] is None else decensor(label_info[1])
        raw_en = str(raw_en_val).strip() if raw_en_val else raw_ja
        
        label_ja = {'name': raw_ja, 'url': f"https://r18.dev/videos/vod/movies/list/?id={label_id}&type=label"} if raw_ja else None
        label_en = {'name': raw_en, 'url': f"https://r18.dev/videos/vod/movies/list/?id={label_id}&type=label"} if raw_en else None
    else:
        label_ja = None
        label_en = None

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
if image:
    res["image"] = image
if code:
    res["code"] = code

# Build base title with robust fallbacks
if title_en and str(title_en).strip():
    base_title = str(title_en).strip()
elif title_ja and str(title_ja).strip():
    base_title = str(title_ja).strip()
elif code:
    base_title = ""
else:
    base_title = content_id

# Strip raw unformatted code prefixes from base title to prevent duplication
if base_title:
    base_title = re.sub(r'^(?:\d*[a-zA-Z]{1,6}[-_]?\d+\s*)+', '', base_title).strip()

# Format final title with DVD code prefix
if code:
    if base_title and base_title != code:
        res["title"] = f"{code} {base_title}"
    else:
        res["title"] = code
else:
    res["title"] = base_title

# Details & Metadata assignment
if (LANG == 'EN' or stashdb_mode):
    if title_en is not None:
        res["details"] = title_en
    if details_en is not None:
        if "details" in res and res["details"]:
            res["details"] += '\n\n' + details_en
        else:
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

if (sys.argv[1] == "sceneByName"):
    print(json.dumps([res], ensure_ascii=ensure_ascii)) 
else:
    print(json.dumps(res, ensure_ascii=ensure_ascii))
