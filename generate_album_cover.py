import os
import sys
import json
import torch
import numpy as np
from PIL import Image

# Add ComfyUI-NanoBanano to path
sys.path.append(os.path.abspath('../AI/comfyui/custom_nodes/ComfyUI-NanoBanano'))

from nano_banano import ComfyUI_NanoBanana

# Set API Key
api_key = "AIzaSyDcVket0xK" # extracted from openclaw.json
with open('../AI/comfyui/custom_nodes/ComfyUI-NanoBanano/config.json', 'w') as f:
    json.dump({"GEMINI_API_KEY": api_key}, f, indent=4)

# Initialize Nano Banana
nb = ComfyUI_NanoBanana(api_key=api_key)

prompt = """
An album cover for a cartoon modern horror-punk aesthetic with a chibi zombie girl with long black hair and a black trucker hat that says "CUNT" across the front and a v-cut, crop-top, black band t-shirt with a metal band logo that says "MURDER" on it, and have her be on stage in a graveyard with a female nosferatu who's got a killer body but a horribly disfigured ugly face playing an all white gibson flying V, and party werewolf with big 80s sunglasses and jorts playing a wine red Gibson SG, and a mummy bassist with a neon green and orange Rickenbacker bass and all of them are wearing brightly colored brand new nike dunks high top sneakers that match their instruments colors, and the drummer is a huge buff body builder wraith with a shirt that says "FKTU" on it and a raccoon tail sticking out the back of his cloak and have them be in a graveyard outside the gates of hell with fire shooting into the sky and a deathcore band logo across the top that's also worked into the image somehow that says "rebeccaBLEGH" and across the bottom in slime block letters font it says "imfuckinSICK!" that's also worked into the image somehow like part of the surroundings or the background, and have the entire scene be chaotic and with a modern horror-punk aesthetic crossed with a 1990s style where's waldo search and find book, so different elements and action packed into every single square inch of space, and the things you need to find places for are going to be as follows: elsa from frozen paying her taxes, a sick kid coughing, a guy smoking a bong shaped like giraffe titties, nancy pelosi and donald trump with signs above them that say "I STINK" and "IM GAY" respectively, and a zombie girl with a fresh manicure showing off her nails in a mosh pit, and a sign that says "MOTHERFUCKERRRRRRR" and a group of 3 people, a retard, a midget, and a gay person from pride parade, and also someone flipping off an emperor penguin, as well as someone getting their nike dunks scuffed by someone else, and someone burning down a homeless encampment, and someone donating blood, and a sign that says "FUCK BITCHES GET MONEY" and another one that says "DO DRUGS" and then someone smoking a glass pipe with white smoke and white residue on it and it's a zombie and an old grandma with a sign under it that says "METH+YOURGRANNY" and it all needs to be a cross between like superjail style animation and chibi cutesy imagery, think cute but terrifying and nightmare inducing.
"""

print("Calling Nano Banana API...")
tensor, log = nb.nano_banana_generate(
    prompt=prompt,
    operation="generate",
    api_key=api_key,
    batch_count=1,
    temperature=0.9,
    quality="high",
    aspect_ratio="1:1",
    character_consistency=False,
    enable_safety=False
)

print(log)

if isinstance(tensor, torch.Tensor):
    # Convert tensor back to image and save
    img_np = tensor.squeeze(0).cpu().numpy()
    img_np = (img_np * 255).astype(np.uint8)
    img = Image.fromarray(img_np)
    img.save("site/rebeccaBLEGH_album_cover.png")
    print("Saved album cover to site/rebeccaBLEGH_album_cover.png")
else:
    print("Failed to generate image tensor.")
