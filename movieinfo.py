import requests, re, json, os, tempfile, urllib.request, shutil

from telethon import TelegramClient, events

from country_list import countries_for_language

token = os.getenv("TOKEN")
app_id = int(os.getenv("APP_ID"))
app_hash = os.getenv("APP_HASH")
tmdb_key = os.getenv("TMDB_KEY")

bot = TelegramClient('bot', app_id, app_hash).start(bot_token=token)

@bot.on(events.NewMessage(pattern=r'^/m'))
async def send_pic(event):
    chat_id = event.message.chat_id
    msg = re.sub(r'/m\s*', '', event.message.text)
    search_url = 'https://api.themoviedb.org/3/search/movie?api_key='+tmdb_key+'&language=zh-CN&query='+msg
    tmdb_id = requests.get(search_url).json()['results'][0]['id']
    tmdb_info = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'?api_key='+tmdb_key+'&language=zh-CN').json()
    imdb_id = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'/external_ids?api_key='+tmdb_key).json()['imdb_id']
    imdb_rating = re.search(r'"ratingValue">\d\.\d', requests.get('https://www.imdb.com/title/'+imdb_id+'/').text).group()[-3:]
    poster = 'https://www.themoviedb.org/t/p/w600_and_h900_bestv2'+tmdb_info['poster_path']
    countries = dict(countries_for_language('zh_CN'))
    tmdb_credits = requests.get('https://api.themoviedb.org/3/movie/'+str(tmdb_id)+'/credits?api_key='+tmdb_key).json()
    for crew in tmdb_credits['crew']:
            if crew['job'] == 'Director':
                director = crew['name']
                break
    info = '**'+tmdb_info['title']+' '+tmdb_info['original_title']+' ('+tmdb_info['release_date'][:4]+')**\n\n'+tmdb_info['overview']+'\n\n#导演 '+director+'\n#类型 #'+tmdb_info['genres'][0]['name']+' #'+tmdb_info['genres'][1]['name']+'\n#国家 #'+countries[tmdb_info['production_countries'][0]['iso_3166_1']]+'\n#语言 #'+tmdb_info['spoken_languages'][0]['name']+'\n#上映日期 '+tmdb_info['release_date']+'\n#片长 '+str(tmdb_info['runtime'])+'分钟\n#IMDB_'+imdb_rating[0]+' '+imdb_rating
    temp_dir = tempfile.TemporaryDirectory()
    save_path = temp_dir.name+'/'+str(tmdb_id)+'.jpg'
    with urllib.request.urlopen(poster) as response, open(save_path, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)
    await bot.send_file(chat_id, save_path, caption=info)



if __name__ == '__main__':
    bot.start()
    bot.run_until_disconnected()
