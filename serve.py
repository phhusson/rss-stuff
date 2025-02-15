#!/usr/bin/env python3

# This file includes a web server, which translate URLs to RSS, and transform that RSS
# For instance http://localhost:8080/www.cnx-software.com/feed/ will return the RSS feed of CNX Software after transformation
# The server maintains a LRU list of feeds, and will refresh them every hour
# The server also maintains a cache of article titles, to avoid fetching the same article multiple times
import requests
from flask import Flask, Response
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from retitle import new_title
import xml.etree.ElementTree as ET
import datetime

app = Flask(__name__)

# Hashmap of feed URL to modified RSS feed content
retitle_cache = {}
feed_cache = {}

# Fetch the original RSS feed
def fetch_rss(url):
    if url in feed_cache:
        o = feed_cache[url]
        if datetime.datetime.now() - o['time'] < datetime.timedelta(minutes=15):
            print(f"Cache hit for {url}")
            return o['content']

    print(f"Fetching {url}")
    response = requests.get(url)
    response.raise_for_status()
    feed_cache[url] = {'content': response.text, 'time': datetime.datetime.now()}
    return response.text

def refresh_rss(url):
    global retitle_cache
    print(f"Refreshing {url}")
    input_rss_file = fetch_rss(url)
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

        guid_element = item.find('guid')
        if guid_element is not None:
            guid_element.text = "phh-" + guid_element.text

        if title_element is not None and link_element is not None:
            original_title = title_element.text
            modified_title = new_title(link_element.text, original_title)
            title_element.text = modified_title

            # Modify the content to include the original title
            content_element = item.find('content')
            if content_element is not None:
                content_element.text = f"Titre original: {original_title}\n\n{content_element.text}"
            else:
                content_element = item.find('description')
                if content_element is not None:
                    content_element.text = f"Titre original: {original_title}\n\n{content_element.text}"


    tree = ET.ElementTree(root)
    # Write the modified XML tree to string
    modified_rss = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    retitle_cache[url] = modified_rss
    print(f"Refreshed {url}")

def resfresh_rss_with_retry():
    try:
        for url in retitle_cache:
            refresh_rss(url)
    except Exception as e:
        print(f"Failed to refresh {url}: {e}")
        # Dump the whole exception stacktrace
        import traceback
        traceback.print_exc()

# Declare the scheduler
scheduler = BackgroundScheduler()
scheduler.start()

@app.route('/jobs')
def get_jobs():
    jobs = scheduler.get_jobs()
    job_list = [f"Job {job.id}: next run at {job.next_run_time}" for job in jobs]
    return "\n".join(job_list)

# Declare the flask function
# In its current form, it will simply download the RSS feed and return it
@app.route('/<path:url>')
def get_rss(url):
    global retitle_cache
    # Prepend https://
    url = 'https://' + url
    if url in retitle_cache:
        print(f"Cache hit for {url}")
        return Response(retitle_cache[url], mimetype='text/xml')
    
    print(f"Fetching {url}")
    rss = fetch_rss(url)
    # Remove all news from the RSS feed
    # This way, the RSS reader will see the feed, just empty
    # And when the refresh is done, the feed will be populated
    root = ET.fromstring(rss)
    channel = root.find('channel')
    for item in channel.findall('item'):
        channel.remove(item)
    rss = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    retitle_cache[url] = rss

    return Response(rss, mimetype='text/xml')

job = scheduler.add_job(resfresh_rss_with_retry, 'interval', minutes=1, args=[])
atexit.register(lambda: scheduler.shutdown())

# Run the server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

