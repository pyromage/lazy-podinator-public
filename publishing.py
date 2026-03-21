"""Publishing: GCS upload, episode cleanup, and RSS feed generation."""

from datetime import datetime, timedelta
from email.utils import formatdate
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from config import storage_client, BUCKET_NAME, SHOWS


def upload_to_bucket(audio_bytes, show_key):
    """Uploads MP3 to Google Cloud Storage and returns public URL"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"{show_key}/{date_str}_update.mp3"

    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(audio_bytes, content_type="audio/mpeg")

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return public_url


def cleanup_old_episodes(show_key, days_to_keep=30):
    """Delete podcast episodes older than specified days from GCS"""
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=f"{show_key}/")

    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    deleted_count = 0

    for blob in blobs:
        if blob.name.endswith('.mp3'):
            filename = blob.name.split('/')[-1]
            date_str = filename.replace('_update.mp3', '')
            try:
                ep_date = datetime.strptime(date_str, '%Y-%m-%d')
                if ep_date < cutoff_date:
                    print(f"Deleting old episode: {blob.name} (age: {(datetime.now() - ep_date).days} days)")
                    blob.delete()
                    deleted_count += 1
            except ValueError:
                continue

    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} episodes older than {days_to_keep} days for {show_key}")

    return deleted_count


def get_existing_episodes(show_key):
    """Get list of existing episodes from GCS bucket (last 30 days only)"""
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=f"{show_key}/")

    cutoff_date = datetime.now() - timedelta(days=30)
    episodes = []

    for blob in blobs:
        if blob.name.endswith('.mp3'):
            filename = blob.name.split('/')[-1]
            date_str = filename.replace('_update.mp3', '')
            try:
                ep_date = datetime.strptime(date_str, '%Y-%m-%d')
                if ep_date >= cutoff_date:
                    episodes.append({
                        'date': ep_date,
                        'url': f"https://storage.googleapis.com/{BUCKET_NAME}/{blob.name}",
                        'size': blob.size or 0
                    })
            except ValueError:
                continue

    episodes.sort(key=lambda x: x['date'], reverse=True)
    return episodes


def generate_podcast_rss(show_key, config):
    """Generate podcast RSS feed XML for a show"""
    episodes = get_existing_episodes(show_key)

    rss = Element('rss')
    rss.set('version', '2.0')
    rss.set('xmlns:itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')

    channel = SubElement(rss, 'channel')

    SubElement(channel, 'title').text = config['title']
    SubElement(channel, 'link').text = f"https://storage.googleapis.com/{BUCKET_NAME}/{show_key}/feed.xml"
    SubElement(channel, 'language').text = 'en-us'
    SubElement(channel, 'description').text = config.get('description', f"Daily {config['title']} podcast")

    SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author').text = config.get('author', 'Lazy Podinator')
    SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}summary').text = config.get('description', f"Daily {config['title']} podcast")
    SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit').text = 'false'

    category = SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}category')
    category.set('text', config.get('category', 'News'))

    if config.get('artwork'):
        image = SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}image')
        image.set('href', config['artwork'])

    owner = SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}owner')
    SubElement(owner, '{http://www.itunes.com/dtds/podcast-1.0.dtd}name').text = config.get('author', 'Lazy Podinator')
    SubElement(owner, '{http://www.itunes.com/dtds/podcast-1.0.dtd}email').text = config.get('email', 'podcast@example.com')

    for ep in episodes:
        item = SubElement(channel, 'item')
        ep_title = f"{config['title']} - {ep['date'].strftime('%B %d, %Y')}"
        SubElement(item, 'title').text = ep_title
        SubElement(item, 'description').text = f"Daily update for {ep['date'].strftime('%B %d, %Y')}"
        SubElement(item, 'pubDate').text = formatdate(ep['date'].timestamp(), usegmt=True)
        SubElement(item, 'guid').text = ep['url']

        enclosure = SubElement(item, 'enclosure')
        enclosure.set('url', ep['url'])
        enclosure.set('type', 'audio/mpeg')
        enclosure.set('length', str(ep['size']))

        SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}duration').text = config.get('duration', '120')
        SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit').text = 'false'

    xml_str = tostring(rss, encoding='unicode')
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent="  ")


def update_podcast_feeds():
    """Generate and upload RSS feeds for all shows"""
    feed_urls = {}

    for show_key, config in SHOWS.items():
        try:
            print(f"Generating RSS feed for {config['title']}...")
            rss_xml = generate_podcast_rss(show_key, config)

            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"{show_key}/feed.xml")
            blob.upload_from_string(rss_xml, content_type="application/xml")

            feed_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{show_key}/feed.xml"
            feed_urls[show_key] = feed_url
            print(f"✓ Feed updated: {feed_url}")
        except Exception as e:
            print(f"Error generating feed for {show_key}: {e}")

    return feed_urls
