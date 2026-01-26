# Podcast Artwork

Place your podcast cover art images in this directory.

## Requirements

* **Format**: JPG or PNG
* **Size**: 1400x1400 to 3000x3000 pixels (square)
* **Recommended**: 3000x3000 pixels for best quality
* **Naming**: Match your show keys from `shows_config.json`

## Files Needed

Based on your `shows_config.json`, create artwork files named:

* `stablecoin.jpg` - Cover art for "The Stablecoin Ledger"
* `ai.jpg` - Cover art for "AI Morning Brief"

## Generating Artwork

### Free AI Tools

1. **Bing Image Creator** (Best, Free): [bing.com/create](https://www.bing.com/create)
   * Uses DALL-E 3
   * Generate at 1024x1024, then upscale

2. **Leonardo.ai**: [leonardo.ai](https://leonardo.ai)
   * 150 free credits/day

3. **Adobe Firefly**: [firefly.adobe.com](https://firefly.adobe.com)
   * 25 free credits/month

### Example Prompts

**For Stablecoin Show:**
```
Professional podcast cover art, stablecoin and digital payments theme,
minimalist design with gold and blue colors, blockchain aesthetic,
clean modern style, square format, high contrast, 3000x3000px
```

**For AI Show:**
```
Podcast artwork for AI technology news show, abstract neural network,
gradient purple and cyan colors, futuristic minimal design,
professional tech aesthetic, square format, 3000x3000px
```

### Upscaling to 3000x3000

If your generated image is smaller:

**Option 1: Upscayl (Free Desktop App)**
```bash
# Download from: https://upscayl.org
# Open app, select image, upscale to 3000x3000
```

**Option 2: ImageMagick (Command Line)**
```bash
# Install: brew install imagemagick
convert input.png -resize 3000x3000 output.jpg
```

**Option 3: Canva (Web)**
1. Go to [canva.com](https://canva.com)
2. Upload image
3. Resize to 3000x3000
4. Download

## Deployment

When you run `./deploy.sh`, the script will automatically:
1. Upload all artwork files to `gs://YOUR_BUCKET/artwork/`
2. Update URLs in your shows configuration
3. Make artwork publicly accessible

## Testing Locally

You can test without real artwork by creating placeholder images:

```bash
# Create simple placeholder images (requires ImageMagick)
convert -size 3000x3000 xc:blue -pointsize 200 -fill white \
  -gravity center -annotate +0+0 "Stablecoin" artwork/stablecoin.jpg

convert -size 3000x3000 xc:purple -pointsize 200 -fill white \
  -gravity center -annotate +0+0 "AI Brief" artwork/ai.jpg
```
