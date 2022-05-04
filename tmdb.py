import requests, re, psycopg2, os, ffmpeg, random, feedparser, asyncio, aiocron, chinese_converter

from io import BytesIO

from datetime import date

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent

from country_list import countries_for_language

from yt_dlp import YoutubeDL

tmdb_key = os.getenv("TMDB_KEY")
trakt_key = os.getenv("TRAKT_KEY")

langcode = {}
for line in open('langcode'):
    key, value = line.split(' ')
    langcode[key] = value.strip('\n')

genres_dic = {}
for line in open('genres'):
    key, value = line.split(':')
    genres_dic[key] = value.strip('\n')

status_dic = {
        'Returning Series': '在播',
        'Ended': '完结',
        'Canceled': '被砍',
        'In Production': '拍摄中'
        }

def get_age(birthday, deathday):
    b = date.fromisoformat(birthday)
    if deathday:
        d = date.fromisoformat(deathday)
    else:
        d = date.today()
    age = d.year-b.year-((d.month, d.day) < (b.month, b.day))
    return str(age)

def get_year(e):
    if e.get('release_date'):
        year = e.get('release_date')[:4]
    else:
        year = e.get('first_air_date', '')[:4]
    return year

def get_digital_date(tmdb_id):
    digital_date = None
    digital_date_list = []
    request_url = 'https://api.themoviedb.org/3/movie/{}/release_dates?api_key={}'.format(tmdb_id, tmdb_key)
    res = requests.get(request_url).json()
    for result in res.get('results'):
        for d in result.get('release_dates'):
            if d.get('type') == 4:
                digital_date_list.append(date.fromisoformat(d.get('release_date')[:10]))
    digital_date_list.sort()
    try:
        if digital_date_list[0] > date.today():
            digital_date = str(digital_date_list[0])
    except:
        return None
    return digital_date

async def get_zh_name(tmdb_id):
    if not tmdb_id:
        return None
    cur.execute("SELECT zh_name FROM person WHERE tmdb_id = %s;", [tmdb_id])
    try:
        name = cur.fetchone()[0]
        return name
    except:
        request_url = 'https://www.wikidata.org/w/api.php?action=query&format=json&uselang={}&prop=entityterms&generator=search&formatversion=2&gsrsearch=haswbstatement%3A%22P4985%3D{}%22'
        res = requests.get(request_url.format('zh-cn', tmdb_id)).json().get('query', {}).get('pages', [])
        wiki_id = next((item.get('title') for item in res), '')
        request_url = 'https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids={}&languages=zh-cn&languagefallback=1&formatversion=2'.format(wiki_id)
        res = requests.get(request_url).json()
        name = res.get('entities', {}).get(wiki_id, {}).get('labels', {}).get('zh-cn', {}).get('value', '')
        name_lang = res.get('entities', {}).get(wiki_id, {}).get('labels', {}).get('zh-cn', {}).get('language', None)
        if not name_lang in (None, 'en'):
            cur.execute("INSERT INTO person VALUES (%s, %s)", (int(tmdb_id), name))
            conn.commit()
            return name

async def get_gdrive_key(tmdb_id):
    cur.execute("SELECT gdrive_key FROM gdrive_key WHERE tmdb_id = %s;", [tmdb_id])
    try:
        return cur.fetchone()[0]
    except:
        return None

def get_metadata(video_path):
    width, height, duration = 1920, 1080, 0
    try:
        video_streams = ffmpeg.probe(video_path, select_streams="v")["streams"][0]
        height = video_streams["height"]
        width = video_streams["width"]
        duration = int(float(video_streams["duration"]))
    except Exception as e:
        print(e)
    return dict(height=height, width=width, duration=duration)


def get_thumbnail(video_path):
    thumbnail = os.path.dirname(__file__)+'/thumbnail.png'
    ff =    (
            ffmpeg
            .input(video_path, ss='1')
            .output(thumbnail, vframes=1)
            .overwrite_output()
            .run(quiet=True)
        )
    return thumbnail

async def build_msg(cat, tmdb_id):
    request_url = 'https://api.themoviedb.org/3/{}/{}?append_to_response=credits,alternative_titles,external_ids,combined_credits,videos&api_key={}&include_image_language=en,null&include_video_language=en&language=zh-CN'.format(cat, tmdb_id, tmdb_key)
    res = requests.get(request_url).json()
    if not res.get('id'):
        return None
    tmdb_id = res.get('id')
    if cat == 'person':
        zh_name = await get_zh_name(tmdb_id)
    else:
        zh_name = res.get('title', res.get('name', ''))
    name = res.get('original_title') or res.get('original_name') or res.get('name')
    cast = []
    season_info = []
    yt_key = ''
    date = ''
    if cat == 'movie' or cat == 'tv':
        date = res.get('release_date') or res.get('first_air_date') or ''
        genres = ['#'+(genres_dic.get(i.get('name')) or i.get('name')) for i in res.get('genres', [])]
        director_info = next((item for item in res.get('credits', {}).get('crew', []) if item.get('job') == 'Director'), {})
        director_name = await get_zh_name(director_info.get('id')) or director_info.get('name', '')
        creator_info = next((item for item in res.get('created_by', [])), {})
        creator_name = await get_zh_name(creator_info.get('id')) or creator_info.get('name', '')
        cast = [await get_zh_name(item.get('id')) or item.get('name') for item in res.get('credits', {}).get('cast', [])[:6]]
        yt_key = next((i.get('key') for i in res.get('videos').get('results') if i.get('type') == "Trailer" and i.get('site') == "YouTube"), '')
        nextep = ''
        if cat == 'tv':
            if res.get('next_episode_to_air'):
                nextep = 'S{:02d}E{:02d} {}'.format(res.get('next_episode_to_air', {}).get('season_number'), res.get('next_episode_to_air', {}).get('episode_number'), res.get('next_episode_to_air', {}).get('air_date'))
            season_info = ['第{}季 ({}) - 共{}集'.format(item.get('season_number'), '202X' if not item.get('air_date') else item.get('air_date')[:4], item.get('episode_count')) for item in res.get('seasons', []) if not item.get('season_number') == 0]
    birthday = res.get('birthday', '')
    deathday = res.get('deathday', '')
    a_works = [] 
    d_works = []
    if cat == 'person':
        a_credits = res.get('combined_credits', {}).get('cast', [])
        a_credits.sort(reverse=True, key=get_year)
        a_works = ['{} - {}'.format(get_year(item), item.get('name', item.get('title'))) for item in a_credits[:10] if get_year(item)]
        d_credits = res.get('combined_credits', {}).get('crew', [])
        d_credits.sort(reverse=True, key=get_year)
        d_credits_fixed = [item for item in d_credits if item.get('job') == 'Director']
        d_credits_fixed.sort(reverse=True, key=get_year)
        d_works = ['{} - {}'.format(get_year(item), item.get('name', item.get('title'))) for item in d_credits_fixed[:10] if get_year(item)]
    text = '{} {}'.format(zh_name, name) if not zh_name == name else name
    text += ' ({})'.format('' if cat == 'person' else date[:4]) if date else ''
    text += '\n**下一集：{}**'.format(nextep) if nextep else ''
    text += '\n\n{}\n'.format(res.get('overview', '')) if res.get('overview') else ''
    text += '\n导演 {}'.format(director_name) if cat == 'movie' else ''
    text += '\n主创 {}'.format(creator_name) if cat == 'tv' else ''
    text += '\n类型 {}'.format(' '.join(genres[:2])) if cat != 'person' else ''
    text += '\n国家 {}'.format(dict(countries_for_language('zh_CN')).get(next((item for item in res.get('production_countries', [])), {}).get('iso_3166_1'), '')) if cat != 'person' else ''
    text += '\n语言 {}'.format(langcode.get(res.get('original_language'), '')) if cat != 'person' else ''
    text += '\n网络 #{}'.format(re.sub(' ', '_', next((i for i in res.get('networks', [])), {}).get('name', ''))) if cat == 'tv' else ''
    text += '\n状况 {}'.format(status_dic.get(res.get('status'), '')) if cat == 'tv' else ''
    text += '\n首播 {}'.format(date) if cat == 'tv' else ''
    text += '\n上映 {}'.format(date) if cat == 'movie' else ''
    text += '\n片长 {}分钟'.format(res.get('runtime')) if cat == 'movie' and res.get('runtime') else ''
    text += '\n集长 {}分钟'.format(next((i for i in res.get('episode_run_time', [])))) if cat == 'tv' and res.get('episode_run_time') else ''
    text += '\n评分 {}'.format(res.get('vote_average')) if cat != 'person' and res.get('vote_average') != 0.0 else ''
    text += '\n演员 {}'.format('\n         '.join(cast)) if cat != 'person' else ''
    text += '\n\n**预计WEB-DL资源上线日期：{}**'.format(get_digital_date(tmdb_id)) if cat == 'movie' and get_digital_date(tmdb_id) else ''
    text += '\n\n分季概况：\n{}'.format('\n'.join(season_info)) if cat == 'tv' else ''
    text += '\n出生 {}'.format(birthday) if birthday else ''
    text += '\n去世 {}'.format(deathday) if deathday else ''
    text += ' ({}岁)'.format(get_age(birthday, deathday)) if cat == 'person' and birthday else ''
    text += '\n\n近期作品:\n{}'.format('\n'.join(a_works) if len(a_credits) > len(d_credits_fixed) else '\n'.join(d_works)) if cat == 'person' else ''
    dic = {
            'name': '{} {}'.format(zh_name, name) if not zh_name == name else name,
            'img': res.get('poster_path') or res.get('profile_path') or '',
            'yt_key': '' if cat == 'person' or not yt_key else yt_key,
            'gdrive_key': await get_gdrive_key(tmdb_id),
            'text': re.sub(r'\n\w+\s\n', r'\n', text),
            }
    return dic

conn = psycopg2.connect("dbname=tmdb user=root")
cur = conn.cursor()

bot = Client('bot')

@bot.on_message(filters.regex("^/start$|^/start@"))
async def welcome(client, message):
    if message.chat.type == enums.ChatType.PRIVATE:
        text = '请直接发送电影、电视剧标题及演员、导演姓名进行搜索，也可以发送以`tt`开头的IMDB编号检索电影信息'
        await bot.send_message(message.chat.id, text)
    else:
        img = "assets/group_help.png"
        text = '请输入 `@tmdbzh_bot 关键字` 进行inline mode搜索'
        await bot.send_photo(message.chat.id, img, caption=text)

@bot.on_message(filters.regex("^/start\s.+"))
async def answer_parameter(client, message):
    match = re.search(r'([a-z]+)(\d+)', message.text)
    cat = match.group(1)
    tmdb_id = match.group(2)
    dic = await build_msg(cat, tmdb_id)
    img = 'https://oracle.tomyangsh.pw/img'+dic.get('img')
    text = dic.get('text')
    yt_key = dic.get('yt_key')
    button = []
    yt_url = 'https://www.youtube.com/watch?v='
    if yt_key:
        button.append(InlineKeyboardButton("预告片", callback_data=yt_key))
    reply_markup = InlineKeyboardMarkup([button]) if button else None
    if dic.get('img'):
        await bot.send_photo(message.chat.id, img, caption=text, reply_markup=reply_markup)
    else:
        await bot.send_message(message.chat.id, text, reply_markup=reply_markup)

@bot.on_message(filters.regex("^tt\d+$") | filters.regex("/\w+/\d+\?language=zh-CN"))
async def imdb_lookup(client, message):
    await bot.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    if re.match('tt\d+', message.text):
        cat = 'movie'
        tmdb_id = message.text
    else:
        search = re.search(r'/(\w+)/(\d+)\?language=zh-CN', message.text)
        cat = search.group(1)
        tmdb_id = search.group(2)
    dic = await build_msg(cat, tmdb_id)
    if not dic:
        return
    img = 'https://oracle.tomyangsh.pw/img'+dic.get('img')
    text = dic.get('text')
    yt_url = 'https://www.youtube.com/watch?v='
    yt_key = dic.get('yt_key')
    button = []
    if yt_key:
        if message.chat.type == enums.ChatType.PRIVATE:
            button.append(InlineKeyboardButton("预告片", callback_data=yt_key))
        else:
            button.append(InlineKeyboardButton("预告片", url=yt_url+yt_key))
    if dic.get('gdrive_key') and message.chat.id in (-1001345466016, -1001310480238):
        button.append(InlineKeyboardButton("团队盘链接", url='https://drive.google.com/file/d/'+dic.get('gdrive_key')))
    reply_markup = InlineKeyboardMarkup([button]) if button else None
    if img:
        await bot.send_photo(message.chat.id, img, caption=text, reply_markup=reply_markup)
    else:
        await bot.send_message(message.chat.id, text, reply_markup=reply_markup)

def s_filter(_, __, message):
    if (message.chat.type == enums.ChatType.PRIVATE) and (re.match(r'/top|/update|出题', message.text) == None):
        return True
    else:
        return False

search_filter = filters.create(s_filter)

@bot.on_message(filters.text & search_filter)
async def send_search_result(client, message):
    extra = []
    await bot.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    query = message.text
    cur.execute("SELECT tmdb_id FROM person WHERE zh_name = %s;", [query])
    if cur.rowcount == 1:
        tmdb_id = cur.fetchone()[0]
        cat = 'person'
    else:
        request_url = "https://api.themoviedb.org/3/search/multi?api_key={}&language=zh-CN&query={}"
        res = requests.get(request_url.format(tmdb_key, query)).json().get('results') or requests.get(request_url.format(tmdb_key, chinese_converter.to_simplified(query))).json().get('results')
        if not res:
            await bot.send_message(message.chat.id, '好像没搜到，换个名字试试')
            return None
        tmdb_id = res[0].get('id')
        cat = res[0]["media_type"]
        extra = res[1:5]
    dic = await build_msg(cat, tmdb_id)
    img = 'https://oracle.tomyangsh.pw/img'+dic.get('img')
    text = dic.get('text')
    yt_key = dic.get('yt_key')
    buttonlist = []
    yt_url = 'https://www.youtube.com/watch?v='
    if yt_key:
        if message.chat.type == enums.ChatType.PRIVATE:
            buttonlist.append([InlineKeyboardButton("预告片", callback_data=yt_key)])
        else:
            buttonlist.append([InlineKeyboardButton("预告片", url=yt_url+yt_key)])
    if extra:
        for i in extra:
            name = '{} {}'.format(i.get("title") or i.get("name"), i.get("release_date", '')[:4] or i.get("first_air_date", '')[:4] or '')
            cat = i.get("media_type")
            tmdb_id = str(i.get("id"))
            buttonlist.append([InlineKeyboardButton(name, callback_data=cat+tmdb_id)])
    reply_markup = InlineKeyboardMarkup(buttonlist) if buttonlist else None
    if dic.get('img'):
        await bot.send_photo(message.chat.id, img, caption=text, reply_markup=reply_markup)
    else:
        await bot.send_message(message.chat.id, text, reply_markup=reply_markup)

@bot.on_callback_query(filters.regex(r'^[a-z]+\d+$'))
async def send_callback_result(client, callback_query):
    await bot.send_chat_action(callback_query.message.chat.id, enums.ChatAction.TYPING)
    match = re.match(r'([a-z]+)(\d+)', callback_query.data)
    cat = match.group(1)
    tmdb_id = match.group(2)
    dic = await build_msg(cat, tmdb_id)
    img = 'https://oracle.tomyangsh.pw/img'+dic.get('img')
    text = dic.get('text')
    yt_key = dic.get('yt_key')
    button = []
    yt_url = 'https://www.youtube.com/watch?v='
    if yt_key:
        if callback_query.message.chat.type == enums.ChatType.PRIVATE:
            button.append(InlineKeyboardButton("预告片", callback_data=yt_key))
        else:
            button.append(InlineKeyboardButton("预告片", url=yt_url+yt_key))
    if dic.get('gdrive_key') and callback_query.message.chat.id in (-1001345466016, -1001310480238):
        button.append(InlineKeyboardButton("团队盘链接", url='https://drive.google.com/file/d/'+dic.get('gdrive_key')))
    reply_markup = InlineKeyboardMarkup([button]) if button else None
    if dic.get('img'):
        await bot.send_photo(callback_query.message.chat.id, img, caption=text, reply_markup=reply_markup)
    else:
        await bot.send_message(callback_query.message.chat.id, text, reply_markup=reply_markup)
    await bot.answer_callback_query(callback_query.id)

@bot.on_callback_query(~filters.regex(r'^False$') & filters.regex(r'\D'))
async def send_trailer(client, callback_query):
    sending = await bot.send_message(callback_query.message.chat.id, "发送中。。。")
    yt_url = 'https://www.youtube.com/watch?v={}'
    YoutubeDL({"format": "bestvideo[vcodec^=avc]+bestaudio[acodec^=mp4a]/best[vcodec^=avc]/best", "outtmpl": "%(id)s.mp4", "quiet": True}).download(yt_url.format(callback_query.data))
    await bot.send_chat_action(callback_query.message.chat.id, enums.ChatAction.UPLOAD_VIDEO)
    video_name = callback_query.data+'.mp4'
    meta = get_metadata(video_name)
    thumbnail = get_thumbnail(video_name)
    await bot.send_video(callback_query.message.chat.id, video_name, thumb=thumbnail, **meta)
    await bot.delete_messages(callback_query.message.chat.id, sending.id)
    await bot.answer_callback_query(callback_query.id)
    os.unlink(video_name)

@bot.on_inline_query()
async def answer(client, inline_query):
    if not inline_query.query:
        request_url = "https://api.themoviedb.org/3/discover/movie?api_key={}&language=zh-CN".format(tmdb_key)
    else:
        keyword = inline_query.query
        request_url = "https://api.themoviedb.org/3/search/multi?api_key={}&language=zh-CN&query={}".format(tmdb_key, keyword)
    res = requests.get(request_url).json()["results"]
    results=[]
    for i in res[:10]:
        cat = i.get("media_type") or "movie"
        date = i.get('release_date') or i.get('first_air_date') or ''
        img = 'https://oracle.tomyangsh.pw/img{}'.format(i.get("poster_path") or i.get("profile_path", '/'))
        zh_name = i.get("title") or i.get("name")
        ori_name = i.get("original_name") or i.get("name") or i.get("original_title")
        title = '{} {}'.format(zh_name if zh_name != ori_name else '', ori_name)
        title += ' ({})'.format('' if cat == 'person' else date[:4]) if date else ''
        description = i.get("overview", '')
        tmdb_id = str(i.get("id"))
        url = 'https://www.themoviedb.org/{}/{}?language=zh-CN'.format(cat, tmdb_id)
        button = InlineKeyboardButton("更多信息", url='https://t.me/tmdbzh_bot?start='+cat+tmdb_id)
        results.append(InlineQueryResultArticle(title=title, description=description, input_message_content=InputTextMessageContent(title+'\n'+url), thumb_url=img, reply_markup=InlineKeyboardMarkup([[button]])))
    await inline_query.answer(results=results)

def get_rarbg():
    guid = open('/root/tmdb-bot/guid', "r").read()
    feed = feedparser.parse('https://rarbg.to/rssdd.php?category=41')
    item_list = []
    for post in feed.entries:
        if post.guid == guid:
            break
        if re.search('1080p.*WEB', post.title):
            title = re.sub('\.|\[rartv\]', ' ', post.title)
            item = '**'+title+'**\n\n`'+post.link+'`'
            item_list.append(item)
    f = open('/root/tmdb-bot/guid', "w")
    f.write(feed.entries[0].guid)
    return item_list

def get_trakt():
    last_id = open('/root/tmdb-bot/last_id', "r").read()
    trakt_headers = {'trakt-api-key': trakt_key}
    c = requests.get('https://api.trakt.tv/users/tomyangsh/collection/movies', headers=trakt_headers).json()
    id_list = []
    for i in reversed(c[-10:]):
        tmdb_id = str(i.get('movie').get('ids').get('tmdb'))
        if tmdb_id == last_id:
            break
        id_list.append(tmdb_id)
    f = open('/root/tmdb-bot/last_id', "w")
    f.write(str(c[-1].get('movie').get('ids').get('tmdb')))
    return id_list

def get_backdrop(res):
    backdrop_list = res.get('images').get('backdrops')
    if backdrop_list:
        backdrop = random.choice(backdrop_list).get('file_path')
    else:
        backdrop = res.get('poster_path')
    return backdrop

quiz_on = False

@aiocron.crontab('*/10 * * * *')
async def reset():
    global quiz_on
    quiz_on = False

@aiocron.crontab('*/30 * * * *')
async def push_rarbg():
    item_list = get_rarbg()
    for item in item_list:
        await bot.send_message(-1001195256281, item)

@aiocron.crontab('*/20 * * * *')
async def push_trakt():
    id_list = get_trakt()
    for tmdb_id in id_list:
        dic = await build_msg('movie', tmdb_id)
        img = 'https://oracle.tomyangsh.pw/img'+dic.get('img')
        info = '团队盘新增影片： `'+tmdb_id+'`\n'
        info += dic.get('text')
        yt_key = dic.get('yt_key')
        button = []
        yt_url = 'https://www.youtube.com/watch?v='
        if yt_key:
            button.append(InlineKeyboardButton("预告片", url=yt_url+yt_key))
        reply_markup = InlineKeyboardMarkup([button]) if button else None
        if not dic.get('img'):
            await bot.send_message(-1001345466016, info, reply_markup=reply_markup)
            continue
        await bot.send_photo(-1001345466016, img, caption=info, reply_markup=reply_markup)
        cur.execute("INSERT INTO gdrive_key(tmdb_id, gdrive_key) VALUES (%s, '0');", [tmdb_id])
        conn.commit()

@bot.on_message(filters.command('update'))
async def update_gdrive_key(client, message):
    msg = message.text
    match = re.match(r'/update\s+(\d+)\s+(.+)', msg)
    if match:
        cur.execute("UPDATE gdrive_key SET gdrive_key = %s WHERE tmdb_id = %s;", (match.group(2), match.group(1)))
        if cur.rowcount != 0:
            conn.commit()
            await bot.send_message(message.chat.id, '['+match.group(1)+'](https://www.themoviedb.org/movie/'+match.group(1)+')\nhttps://drive.google.com/file/d/'+match.group(2))

@bot.on_message(filters.command('top'))
async def credit_top10(client, message):
    cur.execute("SELECT name, credit FROM user_info ORDER BY credit DESC LIMIT 10;")
    list = cur.fetchall()
    result = '答题得分榜:\n\n'
    for i in list:
        result += str(i[1])+'    '+i[0]+'\n'
    await bot.send_message(message.chat.id, result)

@bot.on_message(filters.regex("^出题$|^出題$"))
async def quiz(client, message):
    global quiz_on
    if quiz_on:
        return
    cur.execute("SELECT id FROM idlist ORDER BY ID DESC LIMIT 1;")
    maxid = cur.fetchone()[0]
    list = [{}, {}, {}, {}]
    for i in list:
        id = random.randint(1, maxid)
        cur.execute("SELECT tmdb_id, zh_title FROM idlist WHERE id = %s;", [id])
        res = cur.fetchone()
        i["tmdb_id"] = res[0]
        i["zh_title"] = res[1]
        i["callback_data"] = 'False'
    correct_id = random.randint(0, 3)
    list[correct_id]["callback_data"] = str(list[correct_id]["tmdb_id"])
    imginfo = requests.get('https://api.themoviedb.org/3/movie/{}?append_to_response=images&api_key={}&include_image_language=en,null'.format(list[correct_id]["tmdb_id"], tmdb_key)).json()
    backdrop = get_backdrop(imginfo)
    if backdrop:
        img = 'https://oracle.tomyangsh.pw/img{}'.format(backdrop)
    else:
        await bot.send_message(message.chat.id, "出题失败。。")
        return
    await bot.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    await bot.send_photo(message.chat.id, img, caption='这部影片的标题是:', reply_markup=InlineKeyboardMarkup([
        [
            InlineKeyboardButton(list[0]["zh_title"], callback_data=list[0]["callback_data"]),
            InlineKeyboardButton(list[1]["zh_title"], callback_data=list[1]["callback_data"])
            ],
        [
            InlineKeyboardButton(list[2]["zh_title"], callback_data=list[2]["callback_data"]),
            InlineKeyboardButton(list[3]["zh_title"], callback_data=list[3]["callback_data"])
            ]
        ]
        )
        )
    quiz_on = True

@bot.on_callback_query(filters.regex(r'^False$'))
async def choice_wrong(client, callback_query):
    await bot.answer_callback_query(callback_query.id, text='错了，菜鸡！', show_alert=True)
    cur.execute("SELECT credit FROM user_info WHERE id = %s;", [callback_query.from_user.id])
    credit = cur.fetchone()[0]
    try:
        if credit < 5:
            cur.execute("UPDATE user_info SET credit = 0 WHERE id = %s;", [callback_query.from_user.id])
            conn.commit()
        else:
            cur.execute("UPDATE user_info SET credit = credit-5 WHERE id = %s;", [callback_query.from_user.id])
            conn.commit()
    except DatabaseError as e:
        print(e)
        cur.execute("ROLLBACK")
        conn.commit()

@bot.on_callback_query(filters.regex(r'^\d+'))
async def choice_correct(client, callback_query):
    cur.execute("SELECT zh_title, ori_title, year FROM idlist WHERE tmdb_id = %s;", [int(callback_query.data)])
    res = cur.fetchone()
    await bot.edit_message_text(callback_query.message.chat.id, callback_query.message.id, '{} 回答正确！\n**{}{} ({})** [链接](https://www.themoviedb.org/movie/{})'.format(callback_query.from_user.first_name, res[0]+' ' if not res[0] == res[1] else '', res[1], res[2], callback_query.data))
    global quiz_on
    quiz_on = False
    await bot.answer_callback_query(callback_query.id)
    try:
        cur.execute("UPDATE user_info SET credit = credit+1 WHERE id = %s;", [callback_query.from_user.id])
        conn.commit()
    except DatabaseError as e:
        print(e)
        cur.execute("ROLLBACK")
        conn.commit()

bot.run()
