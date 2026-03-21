# Podcast Artwork

Place your podcast cover art images in this directory.

## Requirements

* **Format**: JPG or PNG
* **Size**: 1400x1400 to 3000x3000 pixels (square)
* **Recommended**: 3000x3000 pixels for best quality
* **Naming**: Match your show keys from `shows_config.json` (e.g., `my_show.png`)

## Generating Artwork

Any AI image generation tool works. For example, Google Gemini
can generate podcast cover art directly at the required dimensions.

## Deployment

When you run `./scripts/deploy.sh`, artwork files are automatically
uploaded to `gs://YOUR_BUCKET/artwork/` and made publicly accessible.
