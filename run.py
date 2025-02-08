#!/usr/bin/env python3

import feedparser
import readability
import requests
import pickle
import os
import re
import xml.etree.ElementTree as ET
import json

def contains_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def llamacpp_complete(txt):
    data = {
        'stream': False,
        'n_predict': 128,
        "stop": ["</s>", "[/INST]"],
        'temperature': 0.35,
        'top_k': 40,
        'top_p': 0.95,
        'min_p': 0.05,
        'typical_p': 1,
        'cache_prompt': True,
    }

    headers = {'Content-Type': 'application/json'}
    data['prompt'] = txt
    response = requests.post(os.environ['LLAMACPP_SERVER'], data=json.dumps(data), headers=headers)
    return json.loads(response.text)['content']

def extract_answer(txt):
    # Regular expression pattern to match text between '**'
    pattern = r'\*\*(.*?)\*\*'

    # Find all matches
    matches = re.findall(pattern, txt)

    return matches

def new_title(url, orig_title):
    global cache
    article = requests.get(url)
    doc = readability.Document(article.content)
    output = llamacpp_complete(f"""
System: You are a helpful assistant.
User: Voici le contenu d'un article de presse. Construis un résumé, en une ligne très courte, des informations nouvelles de l'article. Cette ligne pourrait servir de titre.
Le titre ne cache pas d'informations, et ne cherche pas à être pute-a-clic.
Nomme directement les éléments importants plutôt que d'utiliser des équivalents génériques.
Écris ton choix de titre final en gras avec **, comme ceci **ceci est mon titre**.
Conserve la langue d'origine de l'article.
Si l'article était en anglais, le nouveau titre doit être en anglais.


```html
{doc.title()}
{doc.summary()}
```

Thoughts: .................................................................
Assistant: """)
    if article in cache:
        new_titles = cache[article]
    else:
        new_titles = extract_answer(output)
    cache[article] = new_titles
    serialize_cache()
    if len(new_titles) != 1:
        print(f"Failed for {url}")
        return orig_title
    if contains_chinese(new_titles[0]):
        del cache[article]
        return orig_title
    return new_titles[0]


def fetch_rss(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text

#orig_rss = fetch_rss("https://www.frandroid.com/feed")
orig_rss = fetch_rss("https://www.cnx-software.com/feed/")

cache = {}
def serialize_cache():
    with open('cache.pickle', 'wb') as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)

with open('cache.pickle', 'rb') as f:
    cache = pickle.load(f)

def modify_rss_titles(input_rss_file, output_rss_file):
    # Parse the input RSS feed
    root = ET.fromstring(input_rss_file)

    # Define the namespace if needed
    namespace = {'atom': 'http://www.w3.org/2005/Atom'}

    # Find all item elements (or entry elements for Atom feeds)
    items = root.findall('.//item', namespace) or root.findall('.//atom:entry', namespace)

    # Iterate through the items and modify the titles
    for item in items:
        # Find the title element
        title_element = item.find('title')
        if title_element is None:
            title_element = item.find('title', namespaces={'atom': 'http://www.w3.org/2005/Atom'})

        # Find the link element
        link_element = item.find('link')
        if link_element is None:
            link_element = item.find('link', namespaces={'atom': 'http://www.w3.org/2005/Atom'})

        if title_element is not None and link_element is not None:
            original_title = title_element.text
            modified_title = new_title(link_element.text, original_title)
            title_element.text = modified_title
            # Modify the content to include the original title
            content_element = item.find('content')
            if content_element is not None:
                content_element.text = f"Titre original: {original_title}\n\n{content_element.text}"


    tree = ET.ElementTree(root)
    # Write the modified XML tree to the output file
    tree.write(output_rss_file, encoding='utf-8', xml_declaration=True)

output_rss_file = 'modified_rss.xml'  # Replace with your desired output file name

modify_rss_titles(orig_rss, output_rss_file)
