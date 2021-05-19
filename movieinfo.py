import requests, re, json, os, urllib.request, shutil, random, traceback, datetime

from io import BytesIO

from datetime import date

from telethon import TelegramClient, events

from country_list import countries_for_language

token = os.getenv("TOKEN")
app_id = int(os.getenv("APP_ID"))
app_hash = os.getenv("APP_HASH")
deepl_key = os.getenv("DEEPL_KEY")
tmdb_key = 'b729fb42b650d53389fb933b99f4b072'
header = {'User-Agent': 'Kodi Movie scraper by Team Kodi'}

tmdb_id = []
for item in open('movieid'):
    tmdb_id.append(item.strip("\n"))

langcode = {}
for line in open('langcode'):
    key, value = line.split(' ')
    langcode[key] = value.strip('\n')

status_dic = {
        'Returning Series': '在播',
        'Ended': '完结',
        'Canceled': '被砍',
        'In Production': '拍摄中'
        }

def get_translation(text):
    url = 'https://api-free.deepl.com/v2/translate'
    payload = {'auth_key': deepl_key, 'text': text, 'target_lang': 'ZH'}
    result = requests.post(url, data=payload).json()['translations'][0]['text']
    return result

def calculateAge(birthday):
    today = date.today()
    age = today.year - int(birthday[:4]) - ((today.month, today.day) < (int(birthday[5:7]), int(birthday[8:])))
    return age

def sort_key(e):
    if e.get('release_date') is not None:
        year = e.get('release_date')[:4]
    else:
        year = e.get('first_air_date')[:4]
    return year

bot = TelegramClient('bot', app_id, app_hash).start(bot_token=token)

@bot.on(events.NewMessage(pattern=r'^/m\s'))
async def movie_info(event):
    chat_id = event.message.chat_id
    msg = re.sub(r'/m\s*', '', event.message.text)
    if re.search(r'\s\d*$', msg):
        search_query = re.match(r'.*\s', msg).group()[:-1]+'&year='+re.search(r'\s\d*$', msg).group()
    else:
        search_query = msg
    search_url = 'https://api.themoviedb.org/3/search/movie?api_key='+tmdb_key+'&language=zh-CN&include_adult=true&query='+search_query
    try:
        tmdb_id = requests.get(search_url).json()['results'][0]['id']
    except:
        await bot.send_message(chat_id, '好像没搜到，换个名字试试')
        return None
    try:
        tmdb_info = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'?api_key='+tmdb_key+'&language=zh-CN').json()
        trailer_list = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'/videos?api_key='+tmdb_key).json()['results']
        trailer_url = None
        for i in trailer_list:
            if i['site'] == 'YouTube':
                if i['type'] == 'Trailer':
                    trailer_url = 'https://www.youtube.com/watch?v='+i['key']
                    break
        if trailer_url is None:
            trailer = ''
        else:
            trailer = ' [预告片]('+trailer_url+')'
        try:
            imdb_id = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'/external_ids?api_key='+tmdb_key).json()['imdb_id']
            imdb_rating = re.search(r'"ratingValue">\d\.\d', requests.get('https://www.imdb.com/title/'+imdb_id+'/').text).group()[-3:]
            imdb_info = '\n#IMDB_'+imdb_rating[0]+' '+imdb_rating
        except:
            imdb_info = ''
        poster = BytesIO(requests.get('https://www.themoviedb.org/t/p/w600_and_h900_bestv2'+tmdb_info['poster_path'], headers=header).content)
        countries = dict(countries_for_language('zh_CN'))
        tmdb_credits = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'/credits?api_key='+tmdb_key).json()
        director = ''
        for crew in tmdb_credits['crew']:
                if crew['job'] == 'Director':
                    director = '\n导演 '+re.sub('（.*）', '', get_translation(crew['name']))
                    break
        language = langcode[tmdb_info['original_language']]
        actors = re.sub('（.*）', '', get_translation(tmdb_credits['cast'][0]['name']))+'\n'
        for item in tmdb_credits['cast'][1:5]:
            actor = re.sub('（.*）', '', get_translation(item['name']))
            actors = actors+'         '+actor+'\n'
        genres = ''
        for genre in tmdb_info['genres'][:2]:
            genres = genres+' #'+genre['name']
        info = '**'+tmdb_info['title']+' '+tmdb_info['original_title']+' ('+tmdb_info['release_date'][:4]+')**'+trailer+'\n\n'+tmdb_info['overview']+'\n'+director+'\n类型'+genres+'\n国家 '+countries[tmdb_info['production_countries'][0]['iso_3166_1']]+'\n语言 '+language+'\n上映 '+tmdb_info['release_date']+'\n片长 '+str(tmdb_info['runtime'])+'分钟\n演员 '+actors+imdb_info
        await bot.send_file(chat_id, poster, caption=info)
    except Exception as e:
        traceback.print_exc()
        await bot.send_message(chat_id, '此片信息不完整，详见：[链接](https://www.themoviedb.org/movie/'+str(tmdb_id)+')')

@bot.on(events.NewMessage(pattern=r'^/t\s'))
async def tv_info(event):
    chat_id = event.message.chat_id
    msg = re.sub(r'/t\s*', '', event.message.text)
    if re.search(r'\s\d*$', msg):
        search_query = re.match(r'.*\s', msg).group()[:-1]+'&first_air_date_year='+re.search(r'\s\d*$', msg).group()
    else:
        search_query = msg
    search_url = 'https://api.themoviedb.org/3/search/tv?api_key='+tmdb_key+'&language=zh-CN&include_adult=true&query='+search_query
    try:
        tmdb_id = requests.get(search_url).json()['results'][0]['id']
    except:
        await bot.send_message(chat_id, '好像没搜到，换个名字试试')
        return None
    try:
        tmdb_info = requests.get('https://api.themoviedb.org/3/tv/'+str(tmdb_id)+'?api_key='+tmdb_key+'&language=zh-CN').json()
        trailer_list = requests.get('https://api.themoviedb.org/3/tv/'+str(tmdb_id)+'/videos?api_key='+tmdb_key).json()['results']
        trailer_url = None
        for i in trailer_list:
            if i['site'] == 'YouTube':
                if i['type'] == 'Trailer':
                    trailer_url = 'https://www.youtube.com/watch?v='+i['key']
                    break
        if trailer_url is None:
            trailer = ''
        else:
            trailer = ' [预告片]('+trailer_url+')'
        imdb_id = requests.get('https://api.themoviedb.org/3/tv/'+str(tmdb_id)+'/external_ids?api_key='+tmdb_key).json()['imdb_id']
        trakt_rating = str(requests.get('https://api.trakt.tv/shows/'+imdb_id+'/ratings', headers={'trakt-api-key': '4fb92befa9b5cf6c00c1d3fecbd96f8992c388b4539f5ed34431372bbee1eca8'}).json()['rating'])[:3]
        poster = BytesIO(requests.get('https://www.themoviedb.org/t/p/w600_and_h900_bestv2'+tmdb_info['poster_path'], headers=header).content)
        countries = dict(countries_for_language('zh_CN'))
        tmdb_credits = requests.get('https://api.themoviedb.org/3/tv/'+str(tmdb_id)+'/credits?api_key='+tmdb_key).json()
        creator = ''
        for person in tmdb_info['created_by']:
                    creator = creator+' '+re.sub('（.*）', '', get_translation(person['name']))
        actors = re.sub('（.*）', '', get_translation(tmdb_credits['cast'][0]['name']))+'\n'
        for item in tmdb_credits['cast'][1:5]:
            actor = re.sub('（.*）', '', get_translation(item['name']))
            actors = actors+'         '+actor+'\n'
        genres = ''
        for genre in tmdb_info['genres'][:2]:
            genres = genres+' #'+genre['name']
        seasons = ''
        for season in tmdb_info['seasons']:
            seasons = seasons+season['name']+' - 共'+str(season['episode_count'])+'集\n'
        status = status_dic[tmdb_info['status']]
        info = '**'+tmdb_info['name']+' '+tmdb_info['original_name']+' ('+tmdb_info['first_air_date'][:4]+')**'+trailer+'\n\n'+tmdb_info['overview']+'\n\n创作'+creator+'\n类型'+genres+'\n国家 '+countries[tmdb_info['origin_country'][0]]+'\n网络 #'+tmdb_info['networks'][0]['name']+'\n状况 '+status+'\n首播 '+tmdb_info['first_air_date']+'\n集长 '+str(tmdb_info['episode_run_time'][0])+'分钟\n演员 '+actors+'\n分季概况：\n'+seasons+'\n#Trakt_'+trakt_rating[0]+' '+trakt_rating
        await bot.send_file(chat_id, poster, caption=info)
    except Exception as e:
        traceback.print_exc()
        await bot.send_message(chat_id, '此剧信息不完整，详见：[链接](https://www.themoviedb.org/tv/'+str(tmdb_id)+')')

@bot.on(events.NewMessage(pattern=r'^/a\s'))
async def actor_info(event):
    search_query = re.sub(r'/a\s*', '', event.message.text)
    search_url = 'https://api.themoviedb.org/3/search/person?api_key='+tmdb_key+'&include_adult=true&query='+search_query
    try:
        tmdb_id = requests.get(search_url).json()['results'][0]['id']
    except:
        await bot.send_message(event.chat_id, '好像没搜到，换个名字试试')
        return None
    tmdb_info = requests.get('https://api.themoviedb.org/3/person/'+str(tmdb_id)+'?api_key='+tmdb_key).json()
    profile = BytesIO(requests.get('https://www.themoviedb.org/t/p/original'+tmdb_info['profile_path'], headers=header).content)
    try:
        birthday = tmdb_info['birthday']
        deathday = tmdb_info['deathday']
        if deathday:
            age = str(int(deathday[:4]) - int(birthday[:4]))
            age_info = '\n出生 '+birthday+'\n去世 '+deathday+' ('+age+'岁)\n'
        else:
            age = str(calculateAge(birthday))
            age_info = '\n出生 '+birthday+' ('+age+'岁)\n'
    except:
        age_info = '\n'
    credits_info = requests.get('https://api.themoviedb.org/3/person/'+str(tmdb_id)+'/combined_credits?language=zh-cn&api_key='+tmdb_key).json()['cast']
    credits_info.sort(reverse=True, key=sort_key)
    recent_credits = ''
    for c in credits_info[:10]:
        recent_credits = recent_credits+'\n'+c.get('release_date', '')[:4]+c.get('first_air_date', '')[:4]+' - '+c.get('title', '')+c.get('name', '')
    info = tmdb_info['name']+age_info+'\n近期作品：'+recent_credits
    await bot.send_file(event.chat_id, profile, caption=info)

@bot.on(events.NewMessage(pattern=r'^/d\s'))
async def actor_info(event):
    search_query = re.sub(r'/d\s*', '', event.message.text)
    search_url = 'https://api.themoviedb.org/3/search/person?api_key='+tmdb_key+'&include_adult=true&query='+search_query
    try:
        tmdb_id = requests.get(search_url).json()['results'][0]['id']
    except:
        await bot.send_message(event.chat_id, '好像没搜到，换个名字试试')
        return None
    tmdb_info = requests.get('https://api.themoviedb.org/3/person/'+str(tmdb_id)+'?api_key='+tmdb_key).json()
    profile = BytesIO(requests.get('https://www.themoviedb.org/t/p/original'+tmdb_info['profile_path'], headers=header).content)
    try:
        birthday = tmdb_info['birthday']
        deathday = tmdb_info['deathday']
        if deathday:
            age = str(int(deathday[:4]) - int(birthday[:4]))
            age_info = '\n出生 '+birthday+'\n去世 '+deathday+' ('+age+'岁)\n'
        else:
            age = str(calculateAge(birthday))
            age_info = '\n出生 '+birthday+' ('+age+'岁)\n'
    except:
        age_info = '\n'
    credits_info = requests.get('https://api.themoviedb.org/3/person/'+str(tmdb_id)+'/combined_credits?language=zh-cn&api_key='+tmdb_key).json()['crew']
    work_list = []
    for i in credits_info:
        if i.get('job') == 'Director':
            work_list.append(i)
    work_list.sort(reverse=True, key=sort_key)
    recent_credits = ''
    for c in work_list[:10]:
        recent_credits = recent_credits+'\n'+c.get('release_date', '')[:4]+c.get('first_air_date', '')[:4]+' - '+c.get('title', '')+c.get('name', '')
    info = tmdb_info['name']+age_info+'\n近期作品：'+recent_credits
    await bot.send_file(event.chat_id, profile, caption=info)

@bot.on(events.NewMessage(pattern=r'^出题$|^出題$'))
async def send_question(event):
    sender = event.message.sender
    id = str(random.choice(tmdb_id))
    tmdb_info = requests.get('https://api.themoviedb.org/3/movie/'+id+'?api_key='+tmdb_key+'&language=zh-CN').json()
    image_list = requests.get('https://api.themoviedb.org/3/movie/'+id+'/images?api_key='+tmdb_key).json()['backdrops']
    try:
        sender_name = sender.first_name
    except:
        sender_name = 'BOSS'
    caption1 = sender_name+' 问，这部'+tmdb_info['release_date'][:4]+'年的'+tmdb_info['genres'][0]['name']+'影片的标题是？(60秒内作答有效)'
    print(tmdb_info['title'])
    title_list = []
    title_info = requests.get('https://api.themoviedb.org/3/movie/'+id+'/alternative_titles?api_key='+tmdb_key+'&country=CN').json()['titles']
    info_url = 'https://www.themoviedb.org/movie/'+str(tmdb_info['id'])   
    for t in title_info:
        title_list.append(t['title'])
    translation_info = requests.get('https://api.themoviedb.org/3/movie/'+id+'/translations?api_key='+tmdb_key+'&country=CN').json()['translations']
    for t in translation_info:
        title_list.append(t['data']['title'])
    try:
        image_url = 'https://www.themoviedb.org/t/p/original'+random.choice(image_list)['file_path']
    except:
        image_url = 'https://www.themoviedb.org/t/p/original'+tmdb_info['poster_path']
    image = BytesIO(requests.get(image_url, headers=header).content)
    try:
        async with bot.conversation(event.message.chat_id, exclusive=False, total_timeout=60) as conv:
            question = await conv.send_file(image, caption=caption1)
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
                            caption2 = responder_name+' 回答正确！\n**'+tmdb_info['title']+' '+tmdb_info['original_title']+' ('+tmdb_info['release_date'][:4]+')** '+'[链接]('+info_url+')'
                            await bot.send_message(event.message.chat_id, caption2, reply_to=response)
                            return
    except Exception as e:
        print(e)
        await bot.edit_message(question, '答题超时，答案：'+tmdb_info['title'])

if __name__ == '__main__':
    bot.start()
    bot.run_until_disconnected()
