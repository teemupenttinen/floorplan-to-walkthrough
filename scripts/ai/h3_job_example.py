"""
Example: photoreal video that follows the Unreal camera path exactly, on a self-hosted ComfyUI.

Idea: the Unreal clip fixes geometry and camera; an edge (Canny) control video made from the Unreal buffer passes
drives a ControlNet; reference images (real photos, developer images, your checked photoreal stills) give materials
and light; the first and last frames are anchored to photoreal stills, so the clip starts and ends on images you
already approved and chains with the next clip.

This uses the node names of one reference-to-video model pack as it was in late 2026 (MiniMax H3 ref2v + turbo LoRA +
Fun ControlNet union patch). Node and file names change between releases: export your own working graph from the
ComfyUI menu (Workflow > Export (API)) and adapt build() to it. The structure stays the same for other models
(Wan VACE, etc.): loaders -> control video -> conditioning with refs -> first/last frame guides -> sampler -> decode.

  COMFY=http://127.0.0.1:8188 python3 h3_job_example.py job.json

job.json:
{
  "name": "kitchen_flyin_v1",
  "control_video": "kit/shots/fly_kitchen/control.mp4",   // make_control.sh output (or omit and set "video" for Canny on the pod)
  "video": "kit/shots/fly_kitchen/motion.mp4",
  "refs": ["kit/shots/fly_kitchen/start_photoreal.png", "references/developer/kitchen.jpg"],
  "first_frame": "kit/shots/fly_kitchen/start_photoreal.png",
  "last_frame": "kit/shots/fly_kitchen/end_photoreal.png",
  "prompt": "prompts/fly_kitchen.txt",
  "seconds": 8.6, "size": [1344, 768], "seed": 1234, "strength": 1.0, "steps": 8
}

Learned the hard way:
- Do not give the Unreal clip itself as a reference video: the result copies the CGI look.
- Canny of the lit render puts edges on sun patches and shadows (black artifacts); use normal + base-colour passes.
- Edge detection on the GPU node ran out of memory at ~240 frames: make the control video with ffmpeg beforehand.
- Frame counts must fit the model's latent stride (here n % 17 == 5 at 24 fps).
- A 10 s segment took ~9 min on a 48 GB GPU; chain longer walks segment by segment, each starting on the previous
  segment's last frame (chain_tools.sh last).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comfy_client import Comfy, Graph  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def frames_for(seconds, fps=24, stride=17, rem=5):
    n = max(rem, round(seconds * fps))
    while n % stride != rem:
        n += 1
    return n


def build(job, names):
    n = job.get("frames") or frames_for(job["seconds"])
    W, H = job.get("size", [1344, 768])
    G = Graph()
    unet = G.node(1, "UNETLoader", unet_name=job.get("unet", "minimax_h3_ref2va_pruned_int8_convrot.safetensors"), weight_dtype="default")
    model = G.node(2, "LoraLoaderModelOnly", model=unet, lora_name=job.get("lora_name", "minimax_h3_ref2v_turbo_8step_v1.1_768p_comfyui_bf16.safetensors"),
                   strength_model=job.get("lora", 0.85))
    vae = G.node(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")
    avae = G.node(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")
    clip = G.node(5, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_int8_convrot.safetensors", type="minimax", device="default")
    patch = G.node(6, "ModelPatchLoader", name="minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors")
    if "control_video" in names:
        control = G.node(8, "VHS_LoadVideo", video=names["control_video"], force_rate=24, custom_width=W, custom_height=H,
                         frame_load_cap=n, skip_first_frames=0, select_every_nth=1, format="None")
    else:
        vid = G.node(7, "VHS_LoadVideo", video=names["video"], force_rate=24, custom_width=W, custom_height=H,
                     frame_load_cap=n, skip_first_frames=0, select_every_nth=1, format="None")
        control = G.node(8, "Canny", image=vid, low_threshold=0.15, high_threshold=0.4)
    cmodel = G.node(9, "MiniMaxH3FunControlNetApply", model=model, model_patch=patch, vae=vae,
                    strength=job.get("strength", 1.0), start_percent=0.0, end_percent=job.get("end_percent", 1.0),
                    control_video=control)
    refs = {"ref_images.ref_image_%d" % k: G.node(20 + k, "LoadImage", image=r) for k, r in enumerate(names["refs"])}
    prompt = job["prompt"]
    if os.path.exists(prompt):
        prompt = open(prompt).read()
    G.g["10"] = {"class_type": "MiniMaxH3ReferenceToVideo",
                 "inputs": dict({"clip": clip, "vae": vae, "audio_vae": avae, "prompt": prompt, "width": W, "height": H,
                                 "length": n, "ref_image_size": "match"}, **refs)}
    cond, latent = ["10", 0], ["10", 1]
    for i, (key, idx) in enumerate((("first_frame", 0), ("last_frame", -1))):
        if key in names:
            img = G.node(30 + 2 * i, "LoadImage", image=names[key])
            G.g[str(31 + 2 * i)] = {"class_type": "MiniMaxH3AddGuide",
                                    "inputs": {"positive": cond, "latent": latent, "frame_idx": idx, "vae": vae, "image": img}}
            cond = [str(31 + 2 * i), 0]        # AddGuide has only a conditioning output; the latent stays the same
    guider = G.node(11, "BasicGuider", model=cmodel, conditioning=cond)
    sched = G.node(12, "BasicScheduler", model=cmodel, scheduler="simple", steps=job.get("steps", 8), denoise=1.0)
    noise = G.node(14, "RandomNoise", noise_seed=job.get("seed", 1234))
    samp = G.node(15, "KSamplerSelect", sampler_name="euler")
    out = G.node(16, "SamplerCustomAdvanced", noise=noise, guider=guider, sampler=samp, sigmas=sched, latent_image=latent)
    img = G.node(17, "VAEDecode", samples=out, vae=vae)
    G.node(19, "VHS_VideoCombine", images=img, frame_rate=24, loop_count=0, filename_prefix="kit/" + job["name"],
           format="video/h264-mp4", pix_fmt="yuv420p", crf=14, save_metadata=False, pingpong=False, save_output=True)
    return G.g


def main():
    job = json.load(open(sys.argv[1]))
    c = Comfy()
    names = {"refs": [c.upload(r) for r in job.get("refs", [])]}
    for key in ("control_video", "video", "first_frame", "last_frame"):
        if job.get(key):
            names[key] = c.upload(job[key])
    outputs = c.run(build(job, names), poll=15)
    c.download_all(outputs, os.path.join(HERE, "out"), prefix=job["name"])


if __name__ == "__main__":
    main()
