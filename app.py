from __future__ import print_function

import flask
from flask import stream_with_context, request, Response
from flask import request, redirect, url_for

from werkzeug.utils import secure_filename

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

#settings.py
import os, re
from fnmatch import filter
# __file__ refers to the file settings.py 
APP_ROOT = os.path.dirname(os.path.abspath(__file__))   # refers to application_top
APP_DATA = os.path.join(APP_ROOT, 'data')

app = flask.Flask(__name__)

colors = {
    'Black': '#000000',
    'Red':   '#FF0000',
    'Green': '#00FF00',
    'Blue':  '#0000FF',
}


# get metadata from plate file csv
def plate_metadata(plate_dir, plate_file):
    
    with open('%s/%s' % (plate_dir,plate_file)) as f:
        content = f.readlines()
            
    string_metadata = ''.join(content[:4]).strip()
    return string_metadata


# write metadata from robot csv to metadata.csv
def write_csv_metadata(plate_dir,
                       coating_ab,
                       prot,
                       ab2,
                       coating_ab_units,
                       prot_units,
                       ab2_units,
                       coating_ab_max,
                       prot_max,
                       plate_files,
                       name):
    
    # TODO random directory    

    # TODO write mean set (mean function)

    output_file = '%s/%s' % (plate_dir,'metadata.csv')

    with open(output_file, 'w') as csvfile:
        fieldnames = ['filename',
                      'metadata',
                     'coating_ab',
                     'coating_ab_max',
                     'coating_ab_units',
                     'prot',
                     'prot_max',
                     'prot_units',
                     'ab2',
                     'ab2_units',
                     'name']

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        
        for plate_file in plate_files:
            # todo sort out the fact the ab/prot names are repeated
            writer.writerow({'filename': plate_file,
                             'metadata': plate_metadata(plate_dir, plate_file),
                             'coating_ab': coating_ab,
                             'coating_ab_max': coating_ab_max,
                             'coating_ab_units': coating_ab_units,
                             'prot': prot,
                             'prot_max': prot_max,
                             'prot_units': prot_units,
                             'ab2': ab2,
                             'ab2_units': ab2_units,
                             'name': name,
                            })

            
def get_index(directory, dirname=None):
    
    index = []
    for x in os.walk('%s/' % directory):
        path = x[0]
        
        r = {}
        r['dir'] = path
        r['dirname'] = os.path.basename(path)
        
        # first result is always parent dir
        if r['dirname'] == '':
            continue
        
        # basic protection against invalid dirs
        r['metadata'] = read_plate_file_to_csv_metadata(path)        
        
        if r['metadata'] != []:
            if dirname and \
                r['dirname'] == dirname:
                index.append(r)                    
                break
            index.append(r)
    
    return index
            

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
                    coating_ab_max,
                    ab2_step=4):

    plate = read_plate_file_to_csv(plate_file_csv)
    mapped_plate = get_mapped_plate(plate)
    well_attr = get_well_attrs(mapped_plate,
                               prot_concentration_high,
                               coating_ab_max,
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

def read_plate_file_to_csv_metadata(plate_dir,
                           plate_filename=None,
                           metadata_filename='metadata.csv'):
    
    csv_list = list()
    metadata_file = '%s/%s' % (plate_dir, metadata_filename)
    
    def get_csv_from_row(row):
        return row.split('=')[1].split(' ')
    
    d = []
    
    try:
    
        with open(metadata_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if plate_filename:
                    if plate_filename == \
                        row['filename']:
                            d.append(row)
                            break
                else:
                    d.append(row)
    except IOError:
        return []

    return d


def create_unique_dir(parent_dir):
    import uuid 
    unique_dir = uuid.uuid4().hex[:6].upper()
    
    full_dir = '%s/%s' % (parent_dir, unique_dir)
    os.makedirs(full_dir)
    
    return full_dir


@app.route("/")
def polynomial():
    
    def get_well_num_from_table_select_num(num, rows, cols):
        row_val = int((num)/cols)
        col_val = int(num%cols)
        numwise = (col_val*rows)+row_val
        numwise = numwise+1 # human readable well
        return numwise
    
    excl = request.args.getlist('exclude')
    
    plate_filename = request.args.get('plate_file', default='161102-001.CSV')
    
    plate_dir = request.args.get('plate_dir', default='example')
    plate_dirname = plate_dir
    plate_dir = plate_dir.replace('\\','').replace('/','')

    if plate_dir:
        plate_dir = '%s/%s' % (APP_DATA, plate_dir)

    plate_file = '%s/%s' % (plate_dir, plate_filename)
        
    md = read_plate_file_to_csv_metadata(plate_dir,
                                         plate_filename)
    
    prot_concentration_high = float(md[0]['prot_max'])

    coating_ab_max = float(md[0]['coating_ab_max'])  
        
    rows = 8.0
    cols = 12.0
    
    df = read_plate_to_df(plate_file,
                     prot_concentration_high,
                     coating_ab_max)

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
    
    
    html = flask.render_template(
        'layouts/index.html',
        plot_script=script, plot_div=div,
        wells=csv_list,
        max_value=max_value,
        md=md[0],
        plate_file=plate_filename,
        plate_dir=plate_dirname
    )
    return encode_utf8(html)

@app.route("/index")
def index():

    html = flask.render_template(
        'layouts/reports.html',
        reports=get_index(APP_DATA)
    )
    return encode_utf8(html)


@app.route('/index/<dirname>')
def index_dirname(dirname):

    html = flask.render_template(
        'layouts/reports.html',
        reports=get_index(APP_DATA,dirname)
    )
    return encode_utf8(html)


ALLOWED_EXTENSIONS = set(['csv', 'CSV'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':

        files = flask.request.files.getlist("file")
        # if user does not select file, browser also
        # submit a empty part without filename
        
        save_dir = create_unique_dir(APP_DATA)
        
        filenames = []
        for file in files:
            if file.filename == '':
                flash('No selected file')
                return redirect(request.url)

            if file and allowed_file(file.filename):

                filename = secure_filename(file.filename)
                file.save(os.path.join(save_dir, filename))
                filenames.append(filename)
        
        write_csv_metadata(save_dir,
                       'coaty',
                       'myprot',
                       'ab2',
                       'ABC',
                       'IJK',
                       'XYZ',
                       float(4),
                       float(2),
                       filenames,
                       'steve report test')
        
        return redirect(url_for('upload_file'))

#def write_csv_metadata(plate_dir,
#                       coating_ab,
#                       prot,
#                       ab2,
#                       coating_ab_units,
#                       prot_units,
#                       ab2_units,
#                       plate_files,
#                       name):    
    
    html = flask.render_template(
        'layouts/upload.html',
    )
    return encode_utf8(html)

if __name__ == "__main__":
    print(__doc__)
    #app.run()
    app.run(host='0.0.0.0', port=5919)