from fastapi import FastAPI
from github import Github
from collections import defaultdict
import requests
import yaml
import json
import re
import os

app = FastAPI()


@app.get("/")
async def read_root():
    return {"Hello": "World"}

@app.get("/alignmentprs")
async def get_alignmentprs(b: str = None):
    if not os.environ.get('GITHUB_TOKEN', None):
        return {'err':'A GITHUB_TOKEN environment variable must be defined!'}
    github_token = os.environ['GITHUB_TOKEN']
    g = Github(github_token)
    res = defaultdict(list)
    query = 'org:openshift author:openshift-bot type:pr state:open ART in:title'
    prs = g.search_issues(query=query, sort="created", order="asc", per_page=200)
    print(f"Gathering {prs.totalCount} prs")
    res['totalCount'] = 0
    for pr in prs:
      title = pr.title
      url = pr.html_url
      #branch = pr.repository.get_pull(pr.number).base.ref # update title to include branch name
      #if b and branch != b:
      #    continue
      #else:
      res["prs"].append({"title": title, "url": url})
      res['totalCount'] = res['totalCount'] + 1
    return json.dumps(dict(res))


@app.get("/image/{image_name}")
async def get_images(image_name: str):
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
