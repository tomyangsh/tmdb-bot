import requests, re, json, os, random, feedparser, aiocron

from io import BytesIO

from datetime import date

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from country_list import countries_for_language

token = os.getenv("TOKEN")
app_id = int(os.getenv("APP_ID"))
app_hash = os.getenv("APP_HASH")
tmdb_key = os.getenv("TMDB_KEY")
trakt_key = os.getenv("TRAKT_KEY")

id_list = tuple(i.strip("\n") for i in open('movieid'))

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

gdrive_dic = json.load(open('gdrive_dic'))

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

def search(cat, message):
    msg = message.text
    arg = re.sub(r'/\w\s*|\s\d\d\d\d', '', msg)
    result = requests.get('https://api.themoviedb.org/3/search/{}?api_key={}&include_adult=true&query={}'.format(cat, tmdb_key, arg)).json()['results']
    try:
        if re.match(r'\d\d\d\d', msg[-4:]):
            for i in result:
                if re.match(msg[-4:], i.get('release_date', '')) or re.match(msg[-4:], i.get('first_air_date', '')):
                    return i.get('id')
        else:
            return result[0].get('id')
    except Exception as e:
        print(e)
        return None

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

def get_zh_name(tmdb_id):
    request_url = 'https://www.wikidata.org/w/api.php?action=query&format=json&uselang={}&prop=entityterms&generator=search&formatversion=2&gsrsearch=haswbstatement%3A%22P4985%3D{}%22'
    res = requests.get(request_url.format('zh-cn', tmdb_id)).json().get('query', {}).get('pages', [])
    wiki_id = next((item.get('title') for item in res), '')
    request_url = 'https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids={}&languages=zh-cn&languagefallback=1&formatversion=2'.format(wiki_id)
    res = requests.get(request_url).json()
    name = res.get('entities', {}).get(wiki_id, {}).get('labels', {}).get('zh-cn', {}).get('value', '')
    return name

def get_backdrop(res):
    backdrop_list = res.get('images').get('backdrops')
    if backdrop_list:
        backdrop = random.choice(backdrop_list).get('file_path')
    else:
        backdrop = res.get('poster_path')
    return backdrop

def get_title_list(res):
    title_list = [res.get('original_title')]
    title_list.extend([item.get('title') for item in res.get('alternative_titles').get('titles', res.get('alternative_titles').get('results')) or [] if item.get('title')])
    title_list.extend([item.get('data').get('title', item.get('data').get('name')) for item in res.get('translations').get('translations') if item.get('data').get('title', item.get('data').get('name'))])
    return title_list

def get_detail(cat, tmdb_id):
    request_url = 'https://api.themoviedb.org/3/{}/{}?append_to_response=credits,alternative_titles,external_ids,combined_credits,videos&api_key={}&include_image_language=en,null&include_video_language=en&language=zh-CN'.format(cat, tmdb_id, tmdb_key)
    res = requests.get(request_url).json()
    tmdb_id = res.get('id')
    if cat == 'person':
        zh_name = get_zh_name(tmdb_id)
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
        cast = [get_zh_name(item.get('id')) or item.get('name') for item in res.get('credits', {}).get('cast', [])[:6]]
        yt_url = 'https://www.youtube.com/watch?v={}'
        yt_key = next((i.get('key') for i in res.get('videos').get('results') if i.get('type') == "Trailer" and i.get('site') == "YouTube"), '')
        if cat == 'tv':
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
    dic = {
            'poster': '' if cat == 'person' else res.get('poster_path'),
            'profile': '' if not cat == 'person' else res.get('profile_path'),
            'zh_name': zh_name,
            'name': name,
            'year': '' if cat == 'person' else date[:4],
            'year_last': '' if not cat == 'tv' or not res.get('status') == "Ended" else res.get('last_air_date')[:4],
            'des': res.get('overview', ''),
            'trailer': '' if cat == 'person' or not yt_key else yt_url.format(yt_key),
            'director': '' if cat == 'person' else get_zh_name(next((item for item in res.get('credits', {}).get('crew', []) if item.get('job') == 'Director'), {}).get('id', '')),
            'genres': '' if cat == 'person' else ' '.join(genres[:2]),
            'country': dict(countries_for_language('zh_CN')).get(next((item for item in res.get('production_countries', [])), {}).get('iso_3166_1'), '') if not cat == 'person' else '',
            'lang': '' if cat == 'person' else langcode.get(res.get('original_language'), ''),
            'date': date,
            'digital_date': '' if not cat == 'movie' else get_digital_date(tmdb_id),
            'gdrive_id': gdrive_dic.get(str(tmdb_id)),
            'lenth': res.get('runtime', '') or next((i for i in res.get('episode_run_time', [])), ''),
            'creator': '' if not cat == 'tv' else get_zh_name(next((item for item in res.get('created_by', [])), {}).get('id', '')),
            'cast': '' if cat == 'person' else '\n         '.join(cast),
            'rating': '' if cat == 'person' else res.get('vote_average'),
            'network': '' if not cat == 'tv' else re.sub(' ', '_', next((i for i in res.get('networks', [])), {}).get('name', '')),
            'status': status_dic.get(res.get('status'), ''),
            'season_info': '' if not cat == 'tv' else '\n'.join(season_info),
            'birthday': birthday,
            'deathday': deathday,
            'age': get_age(birthday, deathday) if birthday else '',
            'a_works': '' if not cat == 'person' else '\n'.join(a_works),
            'd_works': '' if not cat == 'person' else '\n'.join(d_works),
            }
    return dic

def get_image(path):
    base_url = 'https://www.themoviedb.org/t/p/original'
    headers = {'User-Agent': 'Kodi Movie scraper by Team Kodi'}
    image = BytesIO(requests.get(base_url+path, headers=headers).content) if path else None
    if image:
        image.name = 'image.jpg'
    return image

bot = Client('bot', app_id, app_hash, bot_token=token)

@aiocron.crontab('*/30 * * * *')
async def push_rarbg():
    item_list = get_rarbg()
    for item in item_list:
        await bot.send_message(-1001195256281, item)

@aiocron.crontab('*/20 * * * *')
async def push_trakt():
    id_list = get_trakt()
    for tmdb_id in id_list:
        d = get_detail('movie', tmdb_id)
        poster = get_image(d.get('poster'))
        info = '团队盘新增影片：\n'
        info += '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
        info += ' ({})'.format(d.get('year')) if d.get('year') else ''
        info += ' [预告片]({})'.format(d.get('trailer')) if d.get('trailer') else ''
        info += '\n\n{}'.format(d.get('des')) if d.get('des') else ''
        if not poster:
            await bot.send_message(-1001345466016, info)
            continue
        await bot.send_photo(-1001345466016, poster, caption=info)

@bot.on_message(filters.command('m'))
def movie_info(client, message):
    tmdb_id = search('movie', message)
    if tmdb_id is None:
        bot.send_message(message.chat.id, '好像没搜到，换个名字试试')
        return None
    bot.send_chat_action(message.chat.id, "typing")
    d = get_detail('movie', tmdb_id)
    poster = get_image(d.get('poster'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += ' ({})'.format(d.get('year')) if d.get('year') else ''
    info += '\n\n{}\n'.format(d.get('des')) if d.get('des') else '\n'
    info += '\n导演 {}'.format(d.get('director')) if d.get('director') else ''
    info += '\n类型 {}'.format(d.get('genres')) if d.get('genres') else ''
    info += '\n国家 {}'.format(d.get('country')) if d.get('country') else ''
    info += '\n语言 {}'.format(d.get('lang')) if d.get('lang') else ''
    info += '\n上映 {}'.format(d.get('date')) if d.get('date') else ''
    info += '\n片长 {}分钟'.format(d.get('lenth')) if d.get('lenth') else ''
    info += '\n评分 {}'.format(d.get('rating')) if not d.get('rating') == 0 else ''
    info += '\n演员 {}'.format(d.get('cast')) if d.get('cast') else ''
    info += '\n\n**预计WEB-DL资源上线日期：{}**'.format(d.get('digital_date')) if d.get('digital_date') else ''
    if not poster:
        bot.send_message(message.chat.id, info)
        return
    if d.get('trailer'):
        if d.get('gdrive_id') and message.chat.id == -1001345466016:
            bot.send_photo(message.chat.id, poster, caption=info, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("预告片", callback_data=d.get('trailer')), InlineKeyboardButton("团队盘链接", url='https://drive.google.com/file/d/'+d.get('gdrive_id'))]]))
            return
        bot.send_photo(message.chat.id, poster, caption=info, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("预告片", callback_data=d.get('trailer'))]]))
        return
    else:
        bot.send_photo(message.chat.id, poster, caption=info, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("预告片（", url='https://www.youtube.com/watch?v=dQw4w9WgXcQ')]]))

@bot.on_message(filters.command('t'))
def tv_info(client, message):
    tmdb_id = search('tv', message)
    if tmdb_id is None:
        bot.send_message(message.chat.id, '好像没搜到，换个名字试试')
        return None
    bot.send_chat_action(message.chat.id, "typing")
    d = get_detail('tv', tmdb_id)
    poster = get_image(d.get('poster'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += ' ({}-{})'.format(d.get('year'), d.get('year_last')) if d.get('year_last') else ' ({})'.format(d.get('year')) if d.get('year') else ''
    info += '\n\n{}\n'.format(d.get('des')) if d.get('des') else '\n'
    info += '\n创作 {}'.format(d.get('creator')) if d.get('creator') else ''
    info += '\n类型 {}'.format(d.get('genres')) if d.get('genres') else ''
    info += '\n国家 {}'.format(d.get('country')) if d.get('country') else ''
    info += '\n网络 #{}'.format(d.get('network')) if d.get('network') else ''
    info += '\n状况 {}'.format(d.get('status')) if d.get('status') else ''
    info += '\n首播 {}'.format(d.get('date')) if d.get('date') else ''
    info += '\n集长 {}分钟'.format(d.get('lenth')) if d.get('lenth') else ''
    info += '\n评分 {}'.format(d.get('rating')) if not d.get('rating') == 0 else ''
    info += '\n演员 {}'.format(d.get('cast')) if d.get('cast') else ''
    info += '\n\n分季概况：\n{}'.format(d.get('season_info')) if d.get('season_info') else ''
    if not poster:
        bot.send_message(message.chat.id, info)
        return
    if d.get('trailer'):
        bot.send_photo(message.chat.id, poster, caption=info, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("预告片", callback_data=d.get('trailer'))]]))
        return
    else:
        bot.send_photo(message.chat.id, poster, caption=info, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("预告片（", url='https://www.youtube.com/watch?v=dQw4w9WgXcQ')]]))

@bot.on_message(filters.command('a'))
def actor_info(client, message):
    tmdb_id = search('person', message)
    if tmdb_id is None:
        bot.send_message(message.chat.id, '好像没搜到，换个名字试试')
        return None
    bot.send_chat_action(message.chat.id, "typing")
    d = get_detail('person', tmdb_id)
    profile = get_image(d.get('profile'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += '\n出生 {}'.format(d.get('birthday')) if d.get('birthday') else ''
    info += '\n去世 {}'.format(d.get('deathday')) if d.get('deathday') else ''
    info += ' ({}岁)'.format(d.get('age')) if d.get('age') else ''
    info += '\n\n近期作品:\n{}'.format(d.get('a_works')) if d.get('a_works') else ''
    if not profile:
        bot.send_message(message.chat.id, info)
        return
    bot.send_photo(message.chat.id, profile, caption=info)

@bot.on_message(filters.command('d'))
def director_info(client, message):
    tmdb_id = search('person', message)
    if tmdb_id is None:
        bot.send_message(message.chat.id, '好像没搜到，换个名字试试')
        return None
    bot.send_chat_action(message.chat.id, "typing")
    d = get_detail('person', tmdb_id)
    profile = get_image(d.get('profile'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += '\n出生 {}'.format(d.get('birthday')) if d.get('birthday') else ''
    info += '\n去世 {}'.format(d.get('deathday')) if d.get('deathday') else ''
    info += ' ({}岁)'.format(d.get('age')) if d.get('age') else ''
    info += '\n\n近期作品:\n{}'.format(d.get('d_works')) if d.get('d_works') else ''
    if not profile:
        bot.send_message(message.chat.id, info)
        return
    bot.send_photo(message.chat.id, profile, caption=info)

@bot.on_callback_query()
def answer(client, callback_query):
    bot.send_message(callback_query.message.chat.id, callback_query.data, reply_to_message_id=callback_query.message.message_id)
    print(callback_query.from_user.first_name+' '+callback_query.data)
'''
@bot.on(events.NewMessage(pattern=r'^出题$|^出題$'))
async def send_question(event):
    chat_id = event.message.chat_id
    sender = event.message.sender
    tid = str(random.choice(id_list))
    res = requests.get('https://api.themoviedb.org/3/movie/{}?append_to_response=images,alternative_titles,translations&api_key={}&include_image_language=en,null&language=zh-CN'.format(tid, tmdb_key)).json()
    backdrop = get_image(get_backdrop(res))
    zh_title = res.get('title')
    title = res.get('original_title')
    title_list = get_title_list(res)
    year = res.get('release_date')[:4]
    genre = next((i.get('name') for i in res.get('genres', [])), '')
    link = 'https://www.themoviedb.org/movie/{}'.format(res.get('id'))
    try:
        sender_name = sender.first_name or 'BOSS'
    except:
        sender_name = 'BOSS'
    question = '{} 问，这部{}年的 {} 影片的标题是？(60秒内作答有效)'.format(sender_name, year, genre)
    print(title)
    try:
        async with bot.conversation(chat_id, exclusive=False, total_timeout=60) as conv:
            q = await conv.send_message(question, file=backdrop)
            while True:
                response = await conv.get_response()
                try:
                    responder_name = response.sender.first_name
                except:
                    responder_name = 'BOSS'
                answer = response.text
                for a in title_list:
                    if a != '':
                        if re.match(re.escape(a[:5]), answer, re.IGNORECASE):
                            reply = '{} 回答正确！\n**{}{} ({})** [链接]({})'.format(responder_name, zh_title+' ' if not zh_title == title else '', title, year, link)
                            await conv.send_message(reply, reply_to=response)
                            return
    except Exception as e:
        print(e)
        await bot.edit_message(q, '答题超时，答案：{}'.format(zh_title))
'''
bot.run()
