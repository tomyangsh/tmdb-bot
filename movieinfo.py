import requests, re, json, os, urllib.request, shutil, random

from io import BytesIO

from telethon import TelegramClient, events

from country_list import countries_for_language

token = os.getenv("TOKEN")
app_id = int(os.getenv("APP_ID"))
app_hash = os.getenv("APP_HASH")
tmdb_key = 'b729fb42b650d53389fb933b99f4b072'
header = {'user-agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0'}

tmdb_id = []
for item in open('movieid'):
    tmdb_id.append(item.strip("\n"))

bot = TelegramClient('bot', app_id, app_hash).start(bot_token=token)


@bot.on(events.NewMessage(pattern=r'^/m\s'))
async def send_pic(event):
    chat_id = event.message.chat_id
    msg = re.sub(r'/m\s*', '', event.message.text)
    search_url = 'https://api.themoviedb.org/3/search/movie?api_key='+tmdb_key+'&language=zh-CN&query='+msg
    try:
        tmdb_id = requests.get(search_url).json()['results'][0]['id']
    except:
        await bot.send_message(chat_id, '好像没搜到，换个名字试试')
        return None
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
    imdb_id = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'/external_ids?api_key='+tmdb_key).json()['imdb_id']
    imdb_rating = re.search(r'"ratingValue">\d\.\d', requests.get('https://www.imdb.com/title/'+imdb_id+'/').text).group()[-3:]
    poster = BytesIO(requests.get('https://www.themoviedb.org/t/p/w600_and_h900_bestv2'+tmdb_info['poster_path'], headers=header).content)
    countries = dict(countries_for_language('zh_CN'))
    tmdb_credits = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'/credits?api_key='+tmdb_key).json()
    for crew in tmdb_credits['crew']:
            if crew['job'] == 'Director':
                director = crew['name']
                break
    if len(tmdb_info['genres']) >= 2:
        info = '**'+tmdb_info['title']+' '+tmdb_info['original_title']+' ('+tmdb_info['release_date'][:4]+')**'+trailer+'\n\n'+tmdb_info['overview']+'\n\n导演 '+director+'\n类型 #'+tmdb_info['genres'][0]['name']+' #'+tmdb_info['genres'][1]['name']+'\n国家 #'+countries[tmdb_info['production_countries'][0]['iso_3166_1']]+'\n语言 #'+tmdb_info['spoken_languages'][0]['name']+'\n上映 '+tmdb_info['release_date']+'\n片长 '+str(tmdb_info['runtime'])+'分钟\n#IMDB_'+imdb_rating[0]+' '+imdb_rating
    else:
        info = '**'+tmdb_info['title']+' '+tmdb_info['original_title']+' ('+tmdb_info['release_date'][:4]+')**'+trailer+'\n\n'+tmdb_info['overview']+'\n\n导演 '+director+'\n类型 #'+tmdb_info['genres'][0]['name']+'\n国家 #'+countries[tmdb_info['production_countries'][0]['iso_3166_1']]+'\n语言 #'+tmdb_info['spoken_languages'][0]['name']+'\n上映 '+tmdb_info['release_date']+'\n片长 '+str(tmdb_info['runtime'])+'分钟\n#IMDB_'+imdb_rating[0]+' '+imdb_rating
    await bot.send_file(chat_id, poster, caption=info)

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
        async with bot.conversation(event.message.chat_id, exclusive=False, timeout=60) as conv:
            question = await conv.send_file(image, caption=caption1)
            answered = False
            while True:
                response = await conv.get_response()
                try:
                    responder_name = response.sender.first_name
                except:
                    responder_name = 'BOSS'
                answer = response.text
                for a in title_list:
                    if a != '':
                        if re.match(a[:5], answer, re.IGNORECASE):
                            caption2 = responder_name+' 回答正确！\n**'+tmdb_info['title']+' '+tmdb_info['original_title']+' ('+tmdb_info['release_date'][:4]+')** '+'[链接]('+info_url+')'
                            await bot.send_message(event.message.chat_id, caption2, reply_to=response)
                            answered = True
                            break
                if answered:
                    break
    except Exception as e:
        print(e)
    if answered is False:
        await bot.edit_message(question, '答题超时，答案：'+tmdb_info['title'])

if __name__ == '__main__':
    bot.start()
    bot.run_until_disconnected()
