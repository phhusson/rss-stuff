#!/usr/bin/env python3
import readability
import requests
import pickle
import os
import re
import json
import time
from collections import OrderedDict

def contains_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def prompt(txt, for_chat=False):
    if not for_chat:
        return f"""
System: You are a helpful assistant.
User: {txt}
Thoughts: .................................................................
Assistant: """
    return txt

def google_aistudio_complete(txt):
    data = {
        'contents': [{
            'parts': [{'text': prompt(txt, for_chat=True)}]
        }]
    }

    headers = {'Content-Type': 'application/json'}
    response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + os.environ['GOOGLE_AISTUDIO_APIKEY'], data=json.dumps(data), headers=headers)
    j = response.json()
    print(f"Received json {j}")
    return j['candidates'][0]['content']['parts'][0]['text']


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
    data['prompt'] = prompt(txt, for_chat=False)
    response = requests.post(os.environ['LLAMACPP_SERVER'], data=json.dumps(data), headers=headers)
    return json.loads(response.text)['content']

def extract_answer(txt):
    # Regular expression pattern to match text between '**'
    pattern = r'\*\*(.*?)\*\*'

    # Find all matches
    matches = re.findall(pattern, txt)

    return matches

last_serialization = 0
def new_title(url, orig_title):
    global cache, last_serialization
    article = requests.get(url)
    if url in cache:
        return cache[url][0]
    doc = readability.Document(article.content)
    prompt = f"""
 Voici le contenu d'un article de presse. Construis un résumé, en une ligne très courte, des informations nouvelles de l'article. Cette ligne pourrait servir de titre.
Le titre ne cache pas d'informations, et ne cherche pas à être pute-a-clic.
Nomme directement les éléments importants plutôt que d'utiliser des équivalents génériques.
Écris ton choix de titre final en gras avec **, comme ceci **ceci est mon titre**.
Conserve la langue d'origine de l'article.
Si l'article était en anglais, le nouveau titre doit être en anglais.


```html
{doc.title()}
{doc.summary()}
```
"""

    #output = llamacpp_complete()
    output = google_aistudio_complete(prompt)
    # Clean-up output: remove \n, and **

    new_titles = extract_answer(output)

    # Serialize cache if it hasn't been serialized in the last 10 minutes
    if time.time() - last_serialization > 60:
        print("Serializing cache")
        serialize_cache()
        last_serialization = time.time()

    if len(new_titles) != 1:
        print(f"Failed for {url}")
        return orig_title
    if contains_chinese(new_titles[0]):
        return orig_title
    cache[url] = new_titles
    return new_titles[0]

class LRUCache(OrderedDict):
    def __init__(self, capacity: int):
        super().__init__()
        self.capacity = capacity

    def __getitem__(self, key):
        if key not in self:
            return None
        value = super().pop(key)
        self[key] = value
        return value

    def __setitem__(self, key, value):
        if key in self:
            super().pop(key)
        elif len(self) >= self.capacity:
            self.popitem(last=False)
        super().__setitem__(key, value)

cache = LRUCache(100000)

def serialize_cache():
    with open('retitle_cache.pickle', 'wb') as f:
        pickle.dump(dict(cache), f, protocol=pickle.HIGHEST_PROTOCOL)

try:
    with open('retitle_cache.pickle', 'rb') as f:
        cache = pickle.load(f)
except FileNotFoundError:
    pass