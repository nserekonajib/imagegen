from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid
import requests
import json
from pathlib import Path
import base64
import cloudinary
import cloudinary.uploader

# ------------------ CONFIG ------------------ #
TOGETHER_API_KEY = os.getenv(
    "TOGETHER_API_KEY",
    "afe11c3f3160811c9983a7ebc9386b6571f2be44e8bd1ea0bd81df405dd43e8c"
)
OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "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"
)
SITE_URL = "http://127.0.0.1:5000"
SITE_NAME = "AI Image Generator"

# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "dreu4sxrd"),
    api_key=os.getenv("CLOUDINARY_API_KEY", "853629285782169"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", "F8eOJ_VaaaCWceE8beE2NYKWJzY")
)

# Temporary local storage
UPLOAD_FOLDER = Path("generated_images")
UPLOAD_FOLDER.mkdir(exist_ok=True)

# ------------------ APP SETUP ------------------ #
app = Flask(__name__)
CORS(app)

# ------------------ Prompt Enhancement ------------------ #
def enhance_prompt(user_prompt):
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": SITE_URL,
                "X-Title": SITE_NAME,
            },
            data=json.dumps({
                "model": "openai/gpt-oss-20b:free",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Enhance the following prompt for AI image generation, "
                                   f"making it vivid, cinematic, highly detailed (<=1600 chars):\n\n{user_prompt}"
                    }
                ]
            }),
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", user_prompt).strip()
    except Exception as e:
        print(f"[ERROR] Prompt enhancement failed: {e}")
        return user_prompt

# ------------------ Cloudinary Upload ------------------ #
def upload_to_cloudinary(image_path):
    try:
        result = cloudinary.uploader.upload(image_path)
        url = result.get("secure_url")
        print(f"[SUCCESS] Uploaded to Cloudinary: {url}")
        return url
    except Exception as e:
        print(f"[ERROR] Cloudinary upload failed: {e}")
        return None

# ------------------ Image Generation ------------------ #
def generate_images(prompt, num_images=1):
    saved_paths = []
    url = "https://api.together.xyz/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }

    for _ in range(num_images):
        try:
            payload = {"model": "black-forest-labs/FLUX.1-schnell-Free", "prompt": prompt}
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            image_info = data["data"][0]

            if "url" in image_info:
                img_resp = requests.get(image_info["url"], timeout=60)
                img_resp.raise_for_status()
                path = UPLOAD_FOLDER / f"{uuid.uuid4()}.png"
                with open(path, "wb") as f: f.write(img_resp.content)
                saved_paths.append(path)

            elif "b64_json" in image_info:
                path = UPLOAD_FOLDER / f"{uuid.uuid4()}.png"
                with open(path, "wb") as f: f.write(base64.b64decode(image_info["b64_json"]))
                saved_paths.append(path)

        except Exception as e:
            print(f"[ERROR] Image generation failed: {e}")
    return saved_paths

# ------------------ API Route ------------------ #
@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    num_images = int(data.get("num_images", 1))

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    # Step 1: Enhance prompt
    enhanced_prompt = enhance_prompt(prompt)

    # Step 2: Generate local images
    local_images = generate_images(enhanced_prompt, num_images)

    # Step 3: Upload to Cloudinary
    cloud_urls = []
    for img_path in local_images:
        url = upload_to_cloudinary(str(img_path))
        if url:
            cloud_urls.append(url)

    return jsonify({"enhanced_prompt": enhanced_prompt, "images": cloud_urls})

# ------------------ Run App ------------------ #
from waitress import serve

if __name__ == "__main__":
    # Waitress ignores debug mode; use app.debug = True if needed
    serve(app, host="0.0.0.0", port=8880)


