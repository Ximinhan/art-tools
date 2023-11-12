from fastapi import FastAPI
import requests
import yaml
import re
app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/image/{image_name}")
def get_images(image_name: str):
    # url = "https://api.github.com/repos/openshift-eng/ocp-build-data/branches?per_page=100"
    # response = requests.get(url)
    # if response.status_code == 200:
    #     branches = [branch["name"] for branch in response.json()]
    #     pattern = re.compile(r"openshift-\d+\.\d+\d+$")
    #     release_branches = [branch for branch in branches if pattern.match(branch)]
    # else:
    #     print(f"Error fetching branches: {response.status_code}")
    #     return {}
    release_branches = ["openshift-4.15", "openshift-4.14", "openshift-4.13", "openshift-4.12", "openshift-4.11", "openshift-4.10"]
    ret = {}
    for branch in release_branches:
        response = requests.get(f"https://api.github.com/repos/openshift-eng/ocp-build-data/contents/images/{image_name}.yml?ref={branch}")
        if response.status_code == 200:
            ret[branch] = yaml.safe_load(requests.request("GET", response.json()["download_url"]).content)
        else:
            print(f"file not fond: {response.status_code}")
            continue
    return ret
