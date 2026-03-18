import sys, os, json
sys.path.insert(0, os.path.join(os.getcwd(),'skills','comfyui','scripts'))
import comfy_graph
inpath=r'C:\Users\user.V915-31\.openclaw\media\inbound\file_1---0da01cd9-2916-45b8-b0ef-80eb747b4470.jpg'
print('uploading', inpath)
server_name = comfy_graph.upload_image(inpath)
print('uploaded ->', server_name)
wf = comfy_graph.flux2_multiple_angles(server_name, ['front','side','3/4','rear'], filename_prefix='inbound_angles')
BASE = comfy_graph.BASE
payload = json.dumps({'prompt': wf}).encode()
import urllib.request
req = urllib.request.Request(f"{BASE}/prompt", data=payload, headers={'Content-Type':'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=30) as r:
    print('status', r.status)
    print(r.read().decode())
