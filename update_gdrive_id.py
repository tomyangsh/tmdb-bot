import re, json

import xml.etree.ElementTree as ET

tree = ET.parse('videodb.xml')
root = tree.getroot()
dic = {}
for movie in root:
    try:
        dic[movie.findall('uniqueid')[1].text] = re.search('item_id=(.*)&driveid', open(movie.find('filenameandpath').text).read()).group(1)
    except:
        continue
gdrive_dic = open('gdrive_dic', 'w')
gdrive_dic.write(json.dumps(dic))
