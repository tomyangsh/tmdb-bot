import requests, re, json, os, random

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

def get_zh_name(name):
    name = unidecode.unidecode(name)
    request_url = 'https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&sites=enwiki&titles={}&props=labels&languages=zh-cn&languagefallback=1&utf8=1&formatversion=2&normalize=1'.format(name)
    res = requests.get(request_url).json()
    result= list(res.get('entities', {}).values())
    name = next((item.get('labels', {}).get('zh-cn', {}).get('value', '') for item in result), '') or name
    return name

def get_detail(cat, tmdb_id, lang='en-US'):
    request_url = 'https://api.themoviedb.org/3/{}/{}?append_to_response=videos,images,credits,alternative_titles,external_ids,translations,combined_credits&api_key={}&include_image_language=en,null&language={}'.format(cat, tmdb_id, tmdb_key, lang)
    res = requests.get(request_url).json()
    tmdb_id = res.get('id')
    zh_trans = next((item for item in res.get('translations', {}).get('translations', []) if item.get('iso_3166_1') == 'CN' and item.get('iso_639_1') == 'zh'), {}).get('data', {})
    if cat == 'person':
        zh_name = get_zh_name(res.get('name'))
    else:
        zh_name = zh_trans.get('title', zh_trans.get('name', ''))
    name = res.get('original_title') or res.get('original_name') or res.get('name')
    cast = []
    backdrop = []
    season_info = []
    trakt_rating = '0.0'
    yt_key = ''
    date = ''
    imdb_rating = ''
    if cat == 'movie' or cat == 'tv':
        yt_url = 'https://www.youtube.com/watch?v={}'
        yt_key = next((item for item in res.get('videos', {}).get('results', {}) if item['type'] == 'Trailer' and item['site'] == 'YouTube'), {}).get('key', '')
        date = res.get('release_date') or res.get('first_air_date') or ''
        genres = ['#'+genres_dic.get(i.get('name')) for i in res.get('genres', [])]
        cast = [get_zh_name(item.get('name')) for item in res.get('credits', {}).get('cast', [])[:5]]
        imdb_id = res.get('external_ids', {}).get('imdb_id', '')
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
            'zh_name': zh_name+' ' if not zh_name == name else '',
            'name': name,
            'year': '' if cat == 'person' else date[:4],
            'des': zh_trans.get('overview') if zh_trans.get('overview') else res.get('overview', ''),
            'trailer': '' if not yt_key else yt_url.format(yt_key),
            'director': '' if cat == 'person' else get_zh_name(next((item for item in res.get('credits', {}).get('crew', []) if item.get('job') == 'Director'), {}).get('name', '')),
            'genres': '' if cat == 'person' else ' '.join(genres[:2]),
            'country': dict(countries_for_language('zh_CN')).get(next((item for item in res.get('production_countries', [])), {}).get('iso_3166_1'), '') if not cat == 'person' else '',
            'lang': '' if cat == 'person' else langcode.get(res.get('original_language'), ''),
            'date': date,
            'lenth': res.get('runtime', '') or next((i for i in res.get('episode_run_time', [])), ''),
            'creator': '' if not cat == 'tv' else get_zh_name(next((item for item in res.get('created_by', [])), {}).get('name', '')),
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
            'link': 'https://www.themoviedb.org/{}/{}'.format(cat, tmdb_id)
            }
    return dic

def get_imdb_rating(imdb_id):
    imdb_url = 'https://www.imdb.com/title/{}/'
    imdb_rating_regex = re.compile(r'itemprop="ratingValue".*?>.*?([\d.]+).*?<')
    imdb_page = requests.get(imdb_url.format(imdb_id)).text
    match = re.search(imdb_rating_regex, imdb_page)
    if match:
        return match.group(1)
    return ''

def get_image(path):
    base_url = 'https://www.themoviedb.org/t/p/original'
    headers = {'User-Agent': 'Kodi Movie scraper by Team Kodi'}
    image = BytesIO(requests.get(base_url+path, headers=headers).content) if path else None
    return image

bot = TelegramClient('bot', app_id, app_hash).start(bot_token=token)

@bot.on(events.NewMessage(pattern=r'^/m\s'))
async def movie_info(event):
    chat_id = event.message.chat_id
    tmdb_id = search('movie', event)
    if tmdb_id is None:
        await bot.send_message(chat_id, '好像没搜到，换个名字试试')
        return None
    d = get_detail('movie', tmdb_id)
    poster = get_image(d.get('poster'))
    info = '{}{}'.format(d.get('zh_name'), d.get('name'))
    info += ' ({})'.format(d.get('year')) if d.get('year') else ''
    info += ' [预告片]({})'.format(d.get('trailer')) if d.get('trailer') else ''
    info += '\n\n{}\n\n'.format(d.get('des')) if d.get('des') else '\n\n'
    info += '导演 {}\n'.format(d.get('director')) if d.get('director') else ''
    info += '类型 {}\n'.format(d.get('genres')) if d.get('genres') else ''
    info += '国家 {}\n'.format(d.get('country')) if d.get('country') else ''
    info += '语言 {}\n'.format(d.get('lang')) if d.get('lang') else ''
    info += '上映 {}\n'.format(d.get('date')) if d.get('date') else ''
    info += '片长 {}分钟\n'.format(d.get('lenth')) if d.get('lenth') else ''
    info += '演员 {}'.format(d.get('cast')) if d.get('cast') else ''
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
    info = '{}{}'.format(d.get('zh_name'), d.get('name'))
    info += ' ({})'.format(d.get('year')) if d.get('year') else ''
    info += ' [预告片]({})'.format(d.get('trailer')) if d.get('trailer') else ''
    info += '\n\n{}\n\n'.format(d.get('des')) if d.get('des') else '\n\n'
    info += '创作 {}\n'.format(d.get('creator')) if d.get('creator') else ''
    info += '类型 {}\n'.format(d.get('genres')) if d.get('genres') else ''
    info += '国家 {}\n'.format(d.get('country')) if d.get('country') else ''
    info += '网络 #{}\n'.format(d.get('network')) if d.get('network') else ''
    info += '状况 {}\n'.format(d.get('status')) if d.get('status') else ''
    info += '首播 {}\n'.format(d.get('date')) if d.get('date') else ''
    info += '集长 {}分钟\n'.format(d.get('lenth')) if d.get('lenth') else ''
    info += '演员 {}'.format(d.get('cast')) if d.get('cast') else ''
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
    d = get_detail('person', tmdb_id, 'zh-CN')
    profile = get_image(d.get('profile'))
    info = d.get('zh_name')+d.get('name')
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
    d = get_detail('person', tmdb_id, 'zh-CN')
    profile = get_image(d.get('profile'))
    info = d.get('zh_name')+d.get('name')
    info += '\n出生 {}'.format(d.get('birthday')) if d.get('birthday') else ''
    info += '\n去世 {}'.format(d.get('deathday')) if d.get('deathday') else ''
    info += ' ({}岁)'.format(d.get('age')) if d.get('age') else ''
    info += '\n\n近期作品:\n{}'.format(d.get('d_works')) if d.get('d_works') else ''
    await bot.send_message(chat_id, info, file=profile)

if __name__ == '__main__':
    bot.run_until_disconnected()
