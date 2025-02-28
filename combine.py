#! /usr/bin/env python3
"""
Allure static files combiner.

Create single html files with all the allure report data, that can be opened from everywhere.

Example:
    python3 ./combine.py ../allure_gen
"""

# pylint: disable=line-too-long

import os
import re
import base64
import argparse
from shutil import copyfile
from bs4 import BeautifulSoup

sep = os.sep
re_sep = os.sep if os.sep == "/" else r"\\"


def combine_allure(folder, report_name):
    """
    Read all files,
    create server.js,
    then run server.js,
    """

    cur_dir = os.path.dirname(os.path.realpath(__file__))

    print("> Folder to process is " + folder)
    print("> Checking for folder contents")

    files_should_be = ["index.html", "app.js", "styles.css"]

    for file in files_should_be:
        if not os.path.exists(folder + sep + file):
            raise Exception(f"ERROR: File {folder + sep + file} doesnt exists, but it should!")

    default_content_type = "text/plain;charset=UTF-8"

    content_types = {
        "txt": "text/plain;charset=UTF-8",
        "js": "application/javascript",
        "json": "application/json",
        "csv": "text/csv",
        "css": "text/css",
        "html": "text/html",
        "htm": "text/html",
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpg",
        "gif": "image/gif"
    }

    base64_extensions = ["png", "jpeg", "jpg", "gif", "html", "htm"]

    allowed_extensions = list(content_types.keys())

    data = []

    print("> Scanning folder for data files...")
    
    for path, dirs, files in os.walk(folder):
        if files:
            folder_url = re.sub(f"^{folder.rstrip(sep).replace(sep, re_sep)}{re_sep}", "", path)
            if folder_url and folder_url != folder:
                for file in files:
                    file_url = folder_url + sep + file
                    ext = file.split(".")[-1]
                    if ext not in allowed_extensions:
                        print(f"WARNING: Unsupported extension: {ext} (file: {path}{sep}{file}) skipping (supported are: {allowed_extensions}")
                        continue
                    mime = content_types.get(ext, default_content_type)
                    if ext in base64_extensions:
                        with open(path + sep + file, "rb") as f:
                            content = base64.b64encode(f.read())
                    else:
                        with open(path + sep + file, "r", encoding="utf8") as f:
                            content = f.read()

                    data.append({"url": file_url, "mime": mime, "content": content, "base64": (ext in base64_extensions)})

    print(f"Found {len(data)} data files")

    print("> Building server.js file...")

    with open(f"{folder}{sep}server.js", "w", encoding="utf8") as f:
        f.write(r"""
        function _base64ToArrayBuffer(base64) {
            var binary_string = window.atob(base64);
            var len = binary_string.length;
            var bytes = new Uint8Array(len);
            for (var i = 0; i < len; i++) {
                bytes[i] = binary_string.charCodeAt(i);
            }
            return bytes.buffer;
        }

        function _arrayBufferToBase64( buffer ) {
          var binary = '';
          var bytes = new Uint8Array( buffer );
          var len = bytes.byteLength;
          for (var i = 0; i < len; i++) {
             binary += String.fromCharCode( bytes[ i ] );
          }
          return window.btoa( binary );
        }

        document.addEventListener("DOMContentLoaded", function() {
            var old_prefilter = jQuery.htmlPrefilter;

            jQuery.htmlPrefilter = function(v) {
                var regs = [
                    /<a[^>]*href="(?<url>[^"]*)"[^>]*>/,
                    /<img[^>]*src="(?<url>[^"]*)"\/?>/
                ];

                for (i in regs)
                {
                    reg = regs[i];
                    m = reg.exec(v);
                    if (m)
                    {
                        if (m['groups'] && m['groups']['url'])
                        {
                            var url = m['groups']['url'];
                            if (server_data.hasOwnProperty(url))
                            {
                                v = v.replace(url, server_data[url]);
                            }
                        }
                    }
                }

                return old_prefilter(v);
            };
        });

        """)

        f.write("var server_data={\n")
        for d in data:
            url = d['url'].replace(sep, "/")
            b64 = d['base64']
            if b64:
                content = "data:" + d['mime'] + ";base64, " + d['content'].decode("utf-8")
                f.write(f""" "{url}": "{content}", \n""")
            else:
                content = d['content'].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                f.write(f""" "{url}": "{content}", \n""")
        f.write("};\n")

        f.write("    var server = sinon.fakeServer.create();\n")

        for d in data:
            content_type = d['mime']
            url = d['url'].replace(sep, "/")
            f.write("""
                server.respondWith("GET", "{url}", [
                      200, { "Content-Type": "{content_type}" }, server_data["{url}"],
                ]);
            """.replace("{url}", url).replace("{content_type}", content_type))

        f.write("server.autoRespond = true;")

    size = os.path.getsize(f'{folder}{sep}server.js')
    print(f"server.js is build, it's size is: {size} bytes")

    print("> Copying file sinon-9.2.4.js into folder...")
    copyfile("sinon-9.2.4.js", folder + f"{sep}sinon-9.2.4.js")

    print("sinon-9.2.4.js is copied")

    print("> Reading index.html file")
    with open(folder + f"{sep}index.html", "r", encoding="utf8") as f:
        index_html = f.read()

    if "sinon-9.2.4.js" not in index_html:
        print("> Patching index.html file to make it use sinon-9.2.4.js and server.js")
        index_html = index_html.replace("""<script src="app.js"></script>""", """<script src="sinon-9.2.4.js"></script><script src="server.js"></script><script src="app.js"></script>""")

        with open(folder + f"{sep}index.html", "w", encoding="utf8") as f:
            print("> Saving patched index.html file, so It can be opened without --allow-file-access-from-files")
            f.write(index_html)
        print("Done")
    else:
        print("> Skipping patching of index.html as it's already patched")

    print("> Parsing index.html")
    soup = BeautifulSoup(''.join(index_html), features="html.parser")
    print("> Filling script tags with real files contents")
    for tag in soup.findAll('script'):
        file_path = folder + sep + tag['src']
        print("...", tag, file_path)
        with open(file_path, "r", encoding="utf8") as ff:
            file_content = ff.read()
            full_script_tag = soup.new_tag("script")
            full_script_tag.insert(0, file_content)
            tag.replaceWith(full_script_tag)
    print("Done")

    print("> Replacing link tags with style tags with real file contents")
    for tag in soup.findAll('link'):
        if tag['rel'] == ["stylesheet"]:
            file_path = folder + sep + tag['href']
            print("...", tag, file_path)
            with open(file_path, "r", encoding="utf8") as ff:
                file_content = ff.read()
                full_script_tag = soup.new_tag("style")
                full_script_tag.insert(0, file_content)
                tag.replaceWith(full_script_tag)

    print("Done")

    with open(report_name, "w", encoding="utf8") as f:
        f.write(str(soup))

    print(f"> Saving result as", report_name)

    size = os.path.getsize(report_name)
    print(f"Done. Complete file size is:{size}")


if __name__ == '__main__':
    #parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    #parser.add_argument('folder', help='Folder path, where allure static files are located')
    #args = parser.parse_args()

    combine_allure("allure-report", "2022-03-11_regression_report.html")
