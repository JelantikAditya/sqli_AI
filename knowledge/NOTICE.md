# Attribution and curation

`sqli-entries.json` is an editorial adaptation/paraphrase of:

- OWASP Web Security Testing Guide contributors, **v4.2**, WSTG-INPV-05,
  Testing for SQL Injection. Licensed under **CC BY-SA 4.0**.
  https://github.com/OWASP/wstg
- **PayloadsAllTheThings**, SQL Injection and MySQL Injection, by Swissky
  and contributors. **MIT License**, Copyright (c) 2019 Swissky.
  https://github.com/swisskyrepo/PayloadsAllTheThings

The structured corpus is licensed **CC BY-SA 4.0**. Payload examples are labeled
as direct or adapted. Interpretation controls, compatibility cautions and
mitigation recommendations are editorial synthesis, not verbatim source rules
or tested DVWA results. Researcher review remains pending.

`sources.lock.json` records exact upstream commit hashes, document paths, source
and snapshot hashes. Raw snapshots and both complete license texts are restored
with `dvwa/fetch_knowledge_sources.py` into `data/raw/knowledge-sources/`.
For the MySQL document, only the error-based, blind and time-based sections are
stored; original upstream line coordinates are retained in the excerpt JSON.

MIT permission notice: Permission is hereby granted, free of charge, to any
person obtaining a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom
the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
