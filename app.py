from __future__ import print_function

import flask
from flask import stream_with_context, request, Response

import json

import csv, sys
import numpy as np
import pandas as pd

from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.embed import file_html
from bokeh.util.string import encode_utf8

from bokeh.models import ColumnDataSource
from bokeh.models import HoverTool
from collections import OrderedDict
from bokeh.models import Legend

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


def read_plate_file_to_csv(filename):
    
    csv_list = list()
    
    def get_csv_from_row(row):
        return row.split('=')[1].split(' ')
    
    with open(filename) as f:
        content = f.readlines()
    
    for line in content:
        # -1 is not found
        if line.find('Row') > 0:
            csv_list.append(get_csv_from_row(line.strip()))
            
    return csv_list


# from plate array to mapped plate array
def get_mapped_plate(plate, filename='data/elisawells.csv',
                 rows=8, cols=12):
    import csv, sys
    
    row_count = 0
    col_count = 0
    
    mapped_plate = list()
       
    with open(filename, 'rb') as f:
        reader = csv.reader(f)
        col_count_list = list()

        for row in reader:
            row_value = int(row[0])
            ab2_value = float(row[1])
    
            well_pos = row_value
            well_col = abs(well_pos/rows)
            well_row = abs(well_pos%rows)-1
            
            mapped_plate.append((row_value, ab2_value, plate[well_row][well_col]))
            
    return mapped_plate


def get_prot_concentration_step(p_high):
    p = p_high

    return [0, p/8.0, p/4.0, p/2.0, p]

def get_coating_ab_step(a_high):
    p = a_high

    return [p/8.0, p/4.0, p/2.0, p]


def get_well_attrs(mapped_plate, prot_concentration_high, coating_ab, ab2_step):
    prot_step = get_prot_concentration_step(prot_concentration_high)
    coating_step = get_coating_ab_step(coating_ab)

    count = 0
    well_attr = list()
    for i in prot_step:
        for j in coating_step:
            for k in range(ab2_step):
                # join both tuples
                tmp_tup = ((j,i)+(mapped_plate[count]))
                well_attr.append({'coating_ab': tmp_tup[0],
                                  'prot': tmp_tup[1],
                                  'well': tmp_tup[2],
                                  'ab2': tmp_tup[3],
                                  'value': float(tmp_tup[4]),
                                 })
                count = count + 1
    return well_attr


def read_plate_to_df(plate_file_csv,
                    prot_concentration_high,
                    coating_ab,
                    ab2_step=4):

    plate = read_plate_file_to_csv(plate_file_csv)
    mapped_plate = get_mapped_plate(plate)
    well_attr = get_well_attrs(mapped_plate,
                               prot_concentration_high,
                               coating_ab,
                               ab2_step)
    df = pd.DataFrame(well_attr)
    return df


def getitem(obj, item, default):
    if item not in obj:
        return default
    else:
        return obj[item]


def get_df_by_prot_conc(df, prot_conc):
    return df[(df.prot == prot_conc)]


def get_plot_for_prot(df, prot_conc):
    
    color_step = ['blue','red','green','purple']

    prot_conc_0 = get_df_by_prot_conc(df, prot_conc) # not 0!
    
    if prot_conc_0.empty:
        return None
    
    coating_steps = prot_conc_0.coating_ab.unique()   

    # used as a factor (categorical x axis)
    ab2_steps = prot_conc_0.ab2.unique()
    
    # used as a factor (categorical x axis)
    ab2_factor = prot_conc_0.sort_values('ab2') \
        .ab2.unique() \
        .astype(str) \
        .tolist()
    
    range_multiplier = 0.05 # 5%
    x_max_val = df['ab2'].max()*range_multiplier
    y_max_val = df['value'].max()*range_multiplier
    
    # add to max for some room
    x_max = round(df['ab2'].max() + x_max_val)
    # remove from min for equal boundary
    x_min = round(df['ab2'].min() - x_max_val)

    y_max = round(df['value'].max() + y_max_val)
    y_min = round(df['value'].min() - y_max_val)


    p = figure(x_range=ab2_factor,
               y_range=(y_min, y_max),
               tools="pan,box_zoom,reset,save,hover",
               title='Protein-S at %sng/ml' % prot_conc,
               plot_width=950, plot_height=615)
    p.title.text_font_size = "20px"
    p.title.align = "center"
    p.xaxis.axis_label = 'Detection Antibody ug/ml'
    p.yaxis.axis_label = 'Absorbance'
    
    c = 0   

    legends = list()
    for coating in coating_steps:
        
        df_a = prot_conc_0[(prot_conc_0.coating_ab == coating)]

        col_df = df_a.reset_index() # move index to column.
        source = ColumnDataSource(ColumnDataSource.from_df(col_df))

        hover = p.select(dict(type=HoverTool))
        hover.tooltips = OrderedDict([('Well', '@well'),
                                      ('Absorbance', '@value'),
                                      ('Coating mAb', '@coating_ab')]) 
        
        point = p.circle_cross(df_a['ab2'].astype(str), df_a['value'], size=18,
                  color=color_step[c], fill_alpha=0.2, line_width=1,
                  source=source)
        
        legends.append(('Coating mAb: %s' % coating, [point]))
        
        c = c + 1
        

    legend = Legend(legends=legends, location=(0, -380))

    p.add_layout(legend, 'right')
        
    return p   

@app.route("/table")
def table():
    
    prot_concentration_high = 2.0
    coating_ab = 4.0
    rows = 8
    cols = 12
    plate_file = 'data/161102-001.CSV'
    
    df = read_plate_to_df(plate_file,
                     prot_concentration_high,
                     coating_ab)
    
    csv_list = read_plate_file_to_csv(plate_file)
    max_value = int(df['value'].max())
    
    html = flask.render_template(
        'layouts/table.html',
        wells=csv_list,
        max_value=max_value
    ) 
    
    return encode_utf8(html)

@app.route("/")
def polynomial():
    
    def get_well_num_from_table_select_num(num, rows, cols):
        row_val = int((num)/cols)
        col_val = int(num%cols)
        numwise = (col_val*rows)+row_val
        numwise = numwise+1 # human readable well
        return numwise

    prot_concentration_high = request.args.get('prot_conc',
                                               default=2.0,
                                               type=float)
    
    coating_ab = request.args.get('coating_ab',
                                               default=4.0,
                                               type=float)
    
    excl = request.args.getlist('exclude')
    
    print('EXCLUDE')
    print(excl)

    rows = 8.0
    cols = 12.0

    plate_file = 'data/161102-001.CSV'
    
    df = read_plate_to_df(plate_file,
                     prot_concentration_high,
                     coating_ab)

    csv_list = read_plate_file_to_csv(plate_file)
    max_value = int(df['value'].max())
    
    # exclude
    df.loc[:,'exclude'] = pd.Series(False, index=df.index)
    
    for e in excl:
        e = int(e)
        e_well = get_well_num_from_table_select_num(e, rows, cols)
        df.loc[df.well == e_well,('exclude')] = True
    

    plots = list()
    for prot_conc in df.sort_values('prot').prot.unique():
        
        if not df.empty:
            p = get_plot_for_prot(df[(df.exclude == False)], prot_conc)
            if p:
                plots.append(p)
    
    script, div = components(plots)

    # For more details see:
    #   http://bokeh.pydata.org/en/latest/docs/user_guide/embedding.html#components
    #script, div = components(fig)
    # from and to isn't active right now
    html = flask.render_template(
        'layouts/index.html',
        plot_script=script, plot_div=div,
        wells=csv_list,
        max_value=max_value
    )
    return encode_utf8(html)

if __name__ == "__main__":
    print(__doc__)
    #app.run()
    app.run(host='0.0.0.0', port=5919)