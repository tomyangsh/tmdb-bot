import requests, re, json, os, random, feedparser, aiocron

import unidecode

from io import BytesIO

from datetime import date

from telethon import TelegramClient, events

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

def search(cat, event):
    msg = event.message.text
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

def get_trailer(cat, tmdb_id):
    yt_url = 'https://www.youtube.com/watch?v={}'
    request_url = 'https://api.themoviedb.org/3/{}/{}/videos?api_key={}'.format(cat, tmdb_id, tmdb_key)
    res = requests.get(request_url).json()
    yt_key = next((i.get('key') for i in res.get('results', []) if i.get('type') == "Trailer" and i.get('site') == "YouTube"), '')
    return '' if not yt_key else yt_url.format(yt_key)

def get_detail(cat, tmdb_id):
    request_url = 'https://api.themoviedb.org/3/{}/{}?append_to_response=credits,alternative_titles,external_ids,combined_credits&api_key={}&include_image_language=en,null&language=zh-CN'.format(cat, tmdb_id, tmdb_key)
    res = requests.get(request_url).json()
    tmdb_id = res.get('id')
    imdb_id = res.get('external_ids', {}).get('imdb_id', '')
    if cat == 'person':
        zh_name = get_zh_name(tmdb_id)
    else:
        zh_name = res.get('title', res.get('name', ''))
    name = res.get('original_title') or res.get('original_name') or res.get('name')
    cast = []
    season_info = []
    trakt_rating = '0.0'
    yt_key = ''
    date = ''
    imdb_rating = ''
    if cat == 'movie' or cat == 'tv':
        date = res.get('release_date') or res.get('first_air_date') or ''
        genres = ['#'+(genres_dic.get(i.get('name')) or i.get('name')) for i in res.get('genres', [])]
        cast = [get_zh_name(item.get('id')) or item.get('name') for item in res.get('credits', {}).get('cast', [])[:5]]
        if cat == 'movie':
            imdb_rating = get_imdb_rating(imdb_id) if cat == 'movie' else ''
        if cat == 'tv':
            trakt_headers = {'trakt-api-key': trakt_key}
            trakt_rating = str(requests.get('https://api.trakt.tv/shows/{}/ratings'.format(imdb_id), headers=trakt_headers).json()['rating'])[:3] if imdb_id else '0.0'
            season_info = ['第{}季 - 共{}集'.format(item.get('season_number'), item.get('episode_count')) for item in res.get('seasons', []) if not item.get('season_number') == 0]
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
            'des': res.get('overview', ''),
            'trailer': '' if cat == 'person' else get_trailer(cat, tmdb_id),
            'director': '' if cat == 'person' else get_zh_name(next((item for item in res.get('credits', {}).get('crew', []) if item.get('job') == 'Director'), {}).get('id', '')),
            'genres': '' if cat == 'person' else ' '.join(genres[:2]),
            'country': dict(countries_for_language('zh_CN')).get(next((item for item in res.get('production_countries', [])), {}).get('iso_3166_1'), '') if not cat == 'person' else '',
            'lang': '' if cat == 'person' else langcode.get(res.get('original_language'), ''),
            'date': date,
            'lenth': res.get('runtime', '') or next((i for i in res.get('episode_run_time', [])), ''),
            'creator': '' if not cat == 'tv' else get_zh_name(next((item for item in res.get('created_by', [])), {}).get('id', '')),
            'cast': '' if cat == 'person' else '\n         '.join(cast),
            'imdb_rating': '' if not imdb_rating else '#IMDB_{} {}'.format(imdb_rating[:1], imdb_rating),
            'trakt_rating': '' if trakt_rating == '0.0' else '#Trakt_'+trakt_rating[:1]+' '+trakt_rating,
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

def get_imdb_rating(imdb_id):
    omdb_url = 'http://www.omdbapi.com/?apikey=3097cace&i={}'.format(imdb_id)
    res = requests.get(omdb_url).json()
    return res.get('imdbRating', '') if not res.get('imdbRating', '') == 'N/A' else ''

def get_image(path):
    base_url = 'https://www.themoviedb.org/t/p/original'
    headers = {'User-Agent': 'Kodi Movie scraper by Team Kodi'}
    image = BytesIO(requests.get(base_url+path, headers=headers).content) if path else None
    return image

bot = TelegramClient('bot', app_id, app_hash).start(bot_token=token)

@aiocron.crontab('*/30 * * * *')
async def push_rarbg():
    item_list = get_rarbg()
    for item in item_list:
        await bot.send_message(1195256281, item)

@bot.on(events.NewMessage(pattern=r'^/m\s'))
async def movie_info(event):
    chat_id = event.message.chat_id
    tmdb_id = search('movie', event)
    if tmdb_id is None:
        await bot.send_message(chat_id, '好像没搜到，换个名字试试')
        return None
    d = get_detail('movie', tmdb_id)
    poster = get_image(d.get('poster'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += ' ({})'.format(d.get('year')) if d.get('year') else ''
    info += ' [预告片]({})'.format(d.get('trailer')) if d.get('trailer') else ''
    info += '\n\n{}\n'.format(d.get('des')) if d.get('des') else '\n'
    info += '\n导演 {}'.format(d.get('director')) if d.get('director') else ''
    info += '\n类型 {}'.format(d.get('genres')) if d.get('genres') else ''
    info += '\n国家 {}'.format(d.get('country')) if d.get('country') else ''
    info += '\n语言 {}'.format(d.get('lang')) if d.get('lang') else ''
    info += '\n上映 {}'.format(d.get('date')) if d.get('date') else ''
    info += '\n片长 {}分钟'.format(d.get('lenth')) if d.get('lenth') else ''
    info += '\n演员 {}'.format(d.get('cast')) if d.get('cast') else ''
    info += '\n\n{}'.format(d.get('imdb_rating')) if d.get('imdb_rating') else ''
    await bot.send_message(chat_id, info, file=poster)

@bot.on(events.NewMessage(pattern=r'^/t\s'))
async def tv_info(event):
    chat_id = event.message.chat_id
    tmdb_id = search('tv', event)
    if tmdb_id is None:
        await bot.send_message(chat_id, '好像没搜到，换个名字试试')
        return None
    d = get_detail('tv', tmdb_id)
    poster = get_image(d.get('poster'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += ' ({})'.format(d.get('year')) if d.get('year') else ''
    info += ' [预告片]({})'.format(d.get('trailer')) if d.get('trailer') else ''
    info += '\n\n{}\n'.format(d.get('des')) if d.get('des') else '\n'
    info += '\n创作 {}'.format(d.get('creator')) if d.get('creator') else ''
    info += '\n类型 {}'.format(d.get('genres')) if d.get('genres') else ''
    info += '\n国家 {}'.format(d.get('country')) if d.get('country') else ''
    info += '\n网络 #{}'.format(d.get('network')) if d.get('network') else ''
    info += '\n状况 {}'.format(d.get('status')) if d.get('status') else ''
    info += '\n首播 {}'.format(d.get('date')) if d.get('date') else ''
    info += '\n集长 {}分钟'.format(d.get('lenth')) if d.get('lenth') else ''
    info += '\n演员 {}'.format(d.get('cast')) if d.get('cast') else ''
    info += '\n\n分季概况：\n{}'.format(d.get('season_info')) if d.get('season_info') else ''
    info += '\n\n{}'.format(d.get('trakt_rating')) if d.get('trakt_rating') else ''
    await bot.send_message(chat_id, info, file=poster)

@bot.on(events.NewMessage(pattern=r'^/a\s'))
async def actor_info(event):
    chat_id = event.message.chat_id
    tmdb_id = search('person', event)
    if tmdb_id is None:
        await bot.send_message(event.chat_id, '好像没搜到，换个名字试试')
        return None
    d = get_detail('person', tmdb_id)
    profile = get_image(d.get('profile'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += '\n出生 {}'.format(d.get('birthday')) if d.get('birthday') else ''
    info += '\n去世 {}'.format(d.get('deathday')) if d.get('deathday') else ''
    info += ' ({}岁)'.format(d.get('age')) if d.get('age') else ''
    info += '\n\n近期作品:\n{}'.format(d.get('a_works')) if d.get('a_works') else ''
    await bot.send_message(chat_id, info, file=profile)

@bot.on(events.NewMessage(pattern=r'^/d\s'))
async def director_info(event):
    chat_id = event.message.chat_id
    tmdb_id = search('person', event)
    if tmdb_id is None:
        await bot.send_message(event.chat_id, '好像没搜到，换个名字试试')
        return None
    d = get_detail('person', tmdb_id)
    profile = get_image(d.get('profile'))
    info = '{} {}'.format(d.get('zh_name'), d.get('name')) if not d.get('zh_name') == d.get('name') else d.get('name')
    info += '\n出生 {}'.format(d.get('birthday')) if d.get('birthday') else ''
    info += '\n去世 {}'.format(d.get('deathday')) if d.get('deathday') else ''
    info += ' ({}岁)'.format(d.get('age')) if d.get('age') else ''
    info += '\n\n近期作品:\n{}'.format(d.get('d_works')) if d.get('d_works') else ''
    await bot.send_message(chat_id, info, file=profile)

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

bot.run_until_disconnected()
