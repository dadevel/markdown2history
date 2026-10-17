# Markdown2History

A small Python script that puts all commands from your Markdown notes into your bash history.

~~~ bash
curl -Lo ~/.local/bin/md2hist https://github.com/dadevel/markdown2history/raw/refs/heads/main/md2hist.py && chmod +x ~/.local/bin/md2hist
md2hist ~/notes >> $HISTFILE && history -r
~~~

Correct handling of multi-line commands requires `HISTTIMEFORMAT` to be enabled.
You might also want to check out [Bash FZF History](https://gist.github.com/dadevel/1f1ab318d7073b81447c70e1e8cae37f).
