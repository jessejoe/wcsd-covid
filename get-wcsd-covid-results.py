#!/usr/bin/env python
import os
import re
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlunsplit

saved_html_filename = 'saved_html.json'
# See if there's any cached data saved locally
try:
    with open(saved_html_filename) as f:
        saved_html = json.load(f)
except OSError:
    saved_html = {}


def get_html(url):
    """Get HTML response from URL from either cached object or request"""
    if url not in saved_html:
        print(f'Fetching {url}')
        saved_html[url] = requests.get(url).text
    return saved_html[url]


main_url = 'https://www.williamsvillek12.org/resources/2021-2022_daily_covid-19_report.php'
# Need this for joining URLs later
main_netloc = urlunsplit(urlsplit(main_url)._replace(path=''))

main_html = get_html(main_url)
main_soup = BeautifulSoup(main_html)
main_post = main_soup.find("div", {"class": "post"})

daily_urls = []
for li in main_post.find_all('li'):
    href = li.find('a').get('href')
    full_url = urljoin(main_netloc, href)
    daily_urls.append(full_url)

results_list = []
# Names in report that should be considered the same, probably typos, format is {'Incorrect name': 'Correct name'}
fixed_names = {'Forest Elementary': 'Forest', 'District': 'District Office'}
# URLs are in descending order by default
for daily_url in reversed(daily_urls):
    soup = BeautifulSoup(get_html(daily_url))
    report_title = soup.find("h1", {"class": "page-title"}).get_text()
    print(f'{report_title}:')
    result_dict = {'Report Name': report_title}
    post = soup.find("div", {"class": "post"})
    # Sometimes elements are <p> and sometimes <div>, so just use regex to look for any element with matching text
    # case_elems = post.find_all('div')
    regex = r'(\d+)\s*Case'
    cases_elems = [elem.parent.parent for elem in post(text=re.compile(regex))]
    for cases_elem in cases_elems:
        cases_text = cases_elem.get_text()
        cases_text_no_prefix = re.sub(r'^-\s+', '', cases_text)
        school, cases = (
            result.strip() for result in cases_text_no_prefix.split(':'))
        school = fixed_names[school] if school in fixed_names else school
        cases = re.match(regex, cases).group(1)
        result_dict[school] = int(cases)
        print(f'- {school}: {cases}')
    results_list.append(result_dict)

results_df = pd.DataFrame(results_list)
results_df = results_df.set_index('Report Name')
# Replace missing days NaN with 0
results_df = results_df.fillna(0)

# Create new dataframes for outputs we want
results_df_cumulative = results_df.cumsum()
results_df_5_day_rolling_mean = results_df.rolling(5).mean()

# Save HTML for re-use
with open(saved_html_filename, 'w') as f:
    json.dump(saved_html, f)

# Posting results to Flourish
s = requests.session()


def get_soup(url):
    resp = s.get(url)
    resp.raise_for_status()
    return BeautifulSoup(resp.text)


def get_csrf_token(url):
    soup = get_soup(url)
    return soup.find('input', {'name': 'csrf_token'}).get('value')


# Each Flourish chart has an ID (seen in the URL) and upload ID (may have to look at inspector or html source)
charts = [{
    'id': 7811272,
    'upload_api': 12489630,
    'data': results_df_5_day_rolling_mean
}, {
    'id': 7789940,
    'upload_api': 12457147,
    'data': results_df_cumulative
}]

for chart in charts:
    login_url = 'https://app.flourish.studio/login'
    # Page which contains the login form (used to get csrf)
    upload_url = f'https://app.flourish.studio/visualisation/{chart["id"]}/edit'
    # Actual API endpoint used to upload form
    upload_api = f'https://app.flourish.studio/api/data_table/{chart["upload_api"]}/csv'
    publish_url = f'https://app.flourish.studio/api/visualisation/{chart["id"]}/publish'
    email = os.getenv('FLOURISH_USERNAME')
    password = os.getenv('FLOURISH_PASSWORD')

    csrf = get_csrf_token(login_url)
    resp = s.post(login_url,
                  data={
                      'email': email,
                      'password': password,
                      'csrf_token': csrf
                  })
    resp.raise_for_status()

    csrf = get_csrf_token(upload_url)
    upload_soup = get_soup(upload_url)
    # Regex to find version number in <script> html elements. This is the only place I could find it:
    # <script>
    # 		Flourish.public_url_prefix = "https://public.flourish.studio/";
    # 		Flourish.initVisualisationEditor({"id":868769,"username":"brokenlego","company_type":null,"has_active_subscription":false,"can_make_new_projects":true,"tour_intro_status":3,"role":null,"company_id":null,"features":{},"name":"Null","email":"jesse@jessejoe.com","organisation":null,"organisation_role":null,"organisation_type":null,"company_name":null,"is_business_customer":false,"feature_bundle_name":"Public","show_upgrade_options":true,"support_email":"hello@flourish.studio","further_payment_action_required":null,"can_remove_flourish_attribution":false,"can_download_svg":true,"can_export_images":true,"can_present":true,"template_settings_overrides":{},"min_auto_republish_interval":86400,"is_superuser":false}, new Flourish.Visualisation(7789940, 29, {"name":"WCSD ...
    regex = r'Flourish.Visualisation\(\d+,\s*(\d*)'
    existing_version = next((re.search(regex, elem).group(1)
                             for elem in upload_soup(text=re.compile(regex))),
                            None)

    # Upload data
    payload = {
        # Important that version is int(), or Flourish appends 1 like it's a string, seems like a bug on their side
        # e.g. '30' would become '301'
        'version_number': int(existing_version),
        'data': chart['data'].to_csv(),
        'csrf_token': csrf
    }
    resp = s.post(upload_api, json=payload)
    print(resp.text)
    resp.raise_for_status()

    # If CSV upload resulted in changes, publish said changes
    if resp.json()['csv_changed']:
        # Publish chart
        payload = {'csrf_token': csrf}
        resp = s.post(publish_url, json=payload)
        print(resp.text)
        resp.raise_for_status()
