# Platform icons

Four marks vendored from [simple-icons](https://github.com/simple-icons/simple-icons)
16.28.0, fetched from `https://cdn.jsdelivr.net/npm/simple-icons@16.28.0/icons/<slug>.svg`:

| file | slug | title |
|---|---|---|
| xiaohongshu.svg | xiaohongshu | Xiaohongshu |
| wechat.svg | wechat | WeChat |
| linkedin.svg | linkedin | LinkedIn |
| zhihu.svg | zhihu | Zhihu |
| x.svg | x | X |

Vendored rather than fetched at build time so `build-social.py` runs offline and
the row cannot change under us. Each is a single path on a 24x24 viewBox, which
is what `build-social.py` assumes.

Note: shields.io does not serve `logo=linkedin`, which is a gap on the shields
side. simple-icons itself still ships the mark, as above.
