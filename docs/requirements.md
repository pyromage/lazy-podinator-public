# Lazy Podinator Requirements

## Summary

This tool is a daily personal podcast generator that takes in content from RSS feeds and Email digests and summarizes the most interesting topics with a 30 second summary on the key topics.  There are up to 20 topics per day for a total of 10 minutes.  The tool use AI to intelligently select topics and provide the podcast scripts to be converted to audio.

## Requirements

### Flow

1. At 8:00 am EST the podcast is created
1. News from the last 3 days is retrieved from various sources
    1. Public RSS feeds
    1. RSS feeds through a users subscription
    1. Email digests to user's gmail inbox
        1. Digest emails will be laballed  
1. News headlines and short summaries of one to two sentences are extracted
1. AI agent intelligently decides on the articles of interest
    1. Agent is provided a short prompt on what the interests are that may be updated by the user in a .json file
    1. Agent decides in which of the specified podcasts, up to 5 to place the content
    1. Agent creates a podcast script of up to a 30 second professional summary of each topic
    1. Agent aggregates all the podcast topic scripts into a single podcast script for each specified podcast.  For exampe podcasts on AI Technology, Stablecoin & Payments, Drone technology etc.
    1. The podcasts and their customized attributes are specified in a .json that can be changed as needed
1. Podcasts are topical "ie update on stablecoin and related payment companies including startups, incumbents and market trends from industry experts".
1. The podcast scripts for each podcast are converted to high quality audio
1. The podcasts are published and can be listened to on spotify or similar free podcast apps

## Other

1. All services must be free for personal use.
1. Daily runs by 8:00 am EST every day
1. Implementation can be developer friendly, ie use free hosting and require code, APIs etc.
