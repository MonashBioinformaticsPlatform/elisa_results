from __future__ import print_function

import flask

import json

import pandas as pd
import numpy as np

from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.embed import file_html
from bokeh.util.string import encode_utf8

#todo remove demo
#http://bokeh.pydata.org/en/latest/docs/user_guide/charts.html
from bokeh.charts import Scatter, output_file, show
from bokeh.sampledata.autompg import autompg as df

app = flask.Flask(__name__)

colors = {
    'Black': '#000000',
    'Red':   '#FF0000',
    'Green': '#00FF00',
    'Blue':  '#0000FF',
}


def getitem(obj, item, default):
    if item not in obj:
        return default
    else:
        return obj[item]


@app.route("/")
def polynomial():
    """ Very simple embedding of a polynomial chart"""
    # Grab the inputs arguments from the URL
    # This is automated by the button
    args = flask.request.args

    # Get all the form arguments in the url with defaults
    color = colors[getitem(args, 'color', 'Black')]
    _from = int(getitem(args, '_from', 0))
    to = int(getitem(args, 'to', 10))

    # Create a polynomial line graph
    x = list(range(_from, to + 1))
    #fig = figure(title="Polynomial")
    #fig.line(x, [i ** 2 for i in x], color=color, line_width=2)
    
    # todo remove demo
    # http://bokeh.pydata.org/en/latest/docs/user_guide/embed.html
    # todo +/- 10%
    
    range_multiplier = 0.05 # 5%
    x_max_val = df['mpg'].max()*range_multiplier
    y_max_val = df['hp'].max()*range_multiplier
    
    # add to max for some room
    x_max = round(df['mpg'].max() + x_max_val)
    # remove from min for equal boundary
    x_min = round(df['mpg'].min() - x_max_val)

    y_max = round(df['hp'].max() + y_max_val)
    y_min = round(df['hp'].min() - y_max_val)
    
    
    p1 = figure(x_range=(x_min, x_max),
                y_range=(y_min, y_max),
                plot_width=650, plot_height=450)
    p1.scatter(df['mpg'], df['hp'], size=12, color='blue', alpha=0.5)
    p2 = figure(x_range=(x_min, x_max),
                y_range=(y_min, y_max),
                plot_width=650, plot_height=450)
    p2.scatter(df['mpg'], df['hp'], size=12, color='green', alpha=0.5)    
    plots = [p1,p2]
    script, div = components(plots)

    # For more details see:
    #   http://bokeh.pydata.org/en/latest/docs/user_guide/embedding.html#components
    #script, div = components(fig)
    # from and to isn't active right now
    html = flask.render_template(
        'layouts/index.html',
        plot_script=script, plot_div=div,
        color=color, _from=_from, to=to
    )
    return encode_utf8(html)

if __name__ == "__main__":
    print(__doc__)
    app.run()