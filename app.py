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
                       ab2_max,
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
                     'ab2_max',
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
                             'ab2_max': ab2_max,
                             'name': name,
                            })

# write exclusions to csv
def write_csv_exclude(plate_file,
                      exclude_list):

    output_file = '%s.exc' % plate_file

    with open(output_file, 'w') as csvfile:
        fieldnames = ['exclude']

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        
        for exclude in exclude_list:
            # todo sort out the fact the ab/prot names are repeated
            writer.writerow({'exclude': exclude,
                            })
            

# from plate array to mapped plate array
def get_csv_exclude(plate_file):
    import csv, sys
       
    exclude = list()
       
    try:
        f = open(plate_file, 'rt')
        
        reader = csv.reader(f)
        reader.next()
        col_count_list = list()
        
        for row in reader:
            row_value = int(row[0])

            exclude.append(row_value)

    except IOError as err:
        print("IO error: {0}".format(err))
        plate_file = plate_file.rsplit('.',1)[0]
        write_csv_exclude(plate_file, list())
    else:
        f.close()
            
    return exclude
            
            
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
        
        # this logic sucks
        found = False
        if r['metadata'] != [] and found == False:
            if dirname and \
                r['dirname'] == dirname:
                found = True
                index.append(r)
        
        if not dirname:
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
def get_mapped_plate(plate, filename='%s/%s' %\
                     (APP_ROOT, 'data/elisawells.csv'),
                 rows=8, cols=12):
    import csv, sys
    
    row_count = 0
    col_count = 0
    
    mapped_plate = list()
       
    with open(filename, 'rt') as f:
        reader = csv.reader(f)
        col_count_list = list()
        
        for row in reader:
            row_value = int(row[0])
            ab2_value = float(row[1])
    
            well_pos = row_value-1
            well_col = int(abs(well_pos/rows))
            well_row = int(abs(well_pos%rows))

            mapped_plate.append((row_value, ab2_value, plate[well_row][well_col]))

    return mapped_plate


def get_prot_concentration_step(p_high):
    p = p_high

    # the -1 is for the final 2 columns that are excluded
    return [0, p/8.0, p/4.0, p/2.0, p, p*-1]

def get_coating_ab_step(a_high):
    p = a_high

    return [p/8.0, p/4.0, p/2.0, p]


def get_well_attrs(mapped_plate, prot_concentration_high, coating_ab,
                   ab2_max, ab2_step):
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
                    ab2_max,
                    ab2_step=4):

    plate = read_plate_file_to_csv(plate_file_csv)
    mapped_plate = get_mapped_plate(plate)
    well_attr = get_well_attrs(mapped_plate,
                               prot_concentration_high,
                               coating_ab_max,
                               ab2_max,
                               ab2_step
                               )

    df = pd.DataFrame(well_attr)
    return df


def getitem(obj, item, default):
    if item not in obj:
        return default
    else:
        return obj[item]


def get_df_by_prot_conc(df, prot_conc):
    return df[(df.prot == prot_conc)]


def get_plot_for_prot(df,
                       coating_ab,
                       prot,
                       ab2,
                       coating_ab_units,
                       prot_units,
                       ab2_units,
                       prot_conc,
                       name):    
    
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
               title='Protein-S: %s at %s %s' % (prot,prot_conc,prot_units),
               plot_width=950, plot_height=615)
    p.title.text_font_size = "20px"
    p.title.align = "center"
    p.xaxis.axis_label = 'Detection Antibody: %s %s' % (ab2, ab2_units)
    p.yaxis.axis_label = 'Absorbance'
    
    c = 0   

    legends = list()
    for coating in coating_steps:
        
        df_a = prot_conc_0[(prot_conc_0.coating_ab == coating)]

        col_df = df_a.reset_index() # move index to column.
        source = ColumnDataSource(ColumnDataSource.from_df(col_df))
        
        coating_name = 'Coating mAb: %s %s' % (coating_ab, coating_ab_units)

        hover = p.select(dict(type=HoverTool))
        hover.tooltips = OrderedDict([('Well', '@well'),
                                      ('Ref', '@well_ref'),
                                      ('Absorbance', '@value'),
                                      (coating_name, '@coating_ab')]) 
        
        point = p.circle_cross(df_a['ab2'].astype(str), df_a['value'], size=18,
                  color=color_step[c], fill_alpha=0.2, line_width=1,
                  source=source)
        
        legends.append(('%s %s' % (coating_name, coating), [point]))
        
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


def process_plate_to_df(plate_file,
                    prot_concentration_high,
                    coating_ab_max,
                    ab2_max=2):
    
    rows = 8.0
    cols = 12.0

    
    # reverse for well display on page..
    def get_well_num_from_table_select_num_rev(num, rows=cols, cols=rows):
        row_val = int((num)/cols)
        col_val = int(num%cols)
        numwise = (col_val*rows)+row_val
        
        # THIS PART IS DIFFERENT
        numwise = numwise # human readable well
        return numwise    

    # get well references
    def get_well_references(well_num, cols=cols):

        well_num = int(well_num)
        cols = int(cols)
        letters = 'ABCDEFGH'
        well_refs = list()

        for i in letters:
            for j in range(1, cols+1):
                well_refs.append('%s%s' % (i,j))

        
        return well_refs[well_num]
    
    df = read_plate_to_df(plate_file,
                         prot_concentration_high,
                         coating_ab_max,
                         ab2_max)
    
    #  well dataframe display
    df['orig_index'] = df.index
    df_well = df.sort(['well'], ascending=[1])
    rowwise = (df_well['well'] - 1).apply(get_well_num_from_table_select_num_rev)
    rowwise = rowwise.rename('well_rowwise')
    df_rowwise = pd.concat([df_well, rowwise], axis=1)
    df_rowwise = df_rowwise.sort(['well_rowwise'], ascending=[1])
    
    #  add well ref
    row_well_ref = (df_rowwise['well_rowwise']).apply(get_well_references)
    row_well_ref = row_well_ref.rename('well_ref')
    df_rowwise = pd.concat([df_rowwise, row_well_ref], axis=1)
    
    # reset for graph
    df = df_rowwise.sort(['orig_index'], ascending=[1])
        
    return df


def get_wells_dict_for_template(df):

    df_rowwise = df.sort(['well_rowwise'], ascending=[1])
    t_df = df_rowwise.reset_index(drop=True)
    wells = t_df.T.to_dict().values()

    return wells


def get_ab2_multiplier(df, max_ab2):
      
    mult = float(max_ab2) / 2.0
    
    df.loc[:,'ab2'] *= mult
    
    return df


def process_exclusions(df, excl, nan=False):
    # todo fix default (aggregate pandas issue)
    rows = 8.0
    cols = 12.0

    def get_well_num_from_table_select_num(num, rows=rows, cols=cols):
        row_val = int((num)/cols)
        col_val = int(num%cols)
        numwise = (col_val*rows)+row_val
        numwise = numwise+1 # human readable well
        return numwise
    
    # exclude
    df.loc[:,'exclude'] = pd.Series(False, index=df.index)
    
    for e in excl:
        e = int(e)
        e_well = get_well_num_from_table_select_num(e, rows, cols)
        df.loc[df.well == e_well,('exclude')] = True
        if nan:
            df.loc[df.well == e_well,('value')] = np.nan
        
    return df


def get_mean_df_from_dir(APP_DATA, dirname,
                    prot_concentration_high,
                    coating_ab_max,
                    ab2_max):
    
    dir_md = get_index(APP_DATA,dirname)
    
    plate_dir = dir_md[0]['dir']
    
    mean_df = pd.DataFrame()
    # for transposing of mean onto structured dataset for plot
    transpose_df = None

    i = 0
    for plate_file in dir_md[0]['metadata']:
        full_filepath = '%s/%s' % (plate_dir, plate_file['filename'])
        #print(full_filepath)
        
        df = process_plate_to_df(full_filepath,
                    prot_concentration_high,
                    coating_ab_max,
                    ab2_max)

        excl = list()
        excl = get_csv_exclude('%s.exc' % full_filepath)

        df = process_exclusions(df, excl, nan=True)

        transpose_df = df

        mean_df['value_%s' % i] = df['value']
        mean_df['exclude_%s' % i] = df['exclude']
        i = i + 1

    transpose_df['value'] = mean_df[['value_0','value_1', 'value_2']].mean(axis=1)
    
    # make sure all 3 plates excluded = NaN mean value
    transpose_df.loc[:,'exclude'] = pd.Series(False, index=df.index)
    transpose_df['exclude'] = transpose_df['value'].isnull()
    return transpose_df


@app.route("/mean", methods=['GET'])
def mean():
    
    # FORM VARS
    excl = list()
    
    plate_dir = request.args.get('plate_dir')
    plate_dirname = plate_dir
    plate_dir = plate_dir.replace('\\','').replace('/','')

    plate_filename = get_index(APP_DATA, plate_dir)[0]['metadata'][0]['filename']
    
    dirname = plate_dir
    plate_dir = get_index(APP_DATA, plate_dir)[0]['dir']
    
    # get plate 1 to grab universal values for the 3 plates
    md = read_plate_file_to_csv_metadata(plate_dir,
                                         plate_filename)
    
    prot_concentration_high = float(md[0]['prot_max'])
    coating_ab_max = float(md[0]['coating_ab_max'])  
    ab2_max = float(md[0]['ab2_max'])
    
    df = get_mean_df_from_dir(APP_DATA, dirname,
                             prot_concentration_high,
                             coating_ab_max,
                             ab2_max)

    max_value = int(df['value'].max())
        
    # to pass through to plate (rowwise)
    # reset index, then transform, to dict
    wells = get_wells_dict_for_template(df)
    
    # exclude wells for graph
    df_plot = df[:80]
    get_ab2_multiplier(df, ab2_max)

    plots = list()
    for prot_conc in df.sort_values('prot').prot.unique():
        
        if not df_plot.empty:
            p = get_plot_for_prot(df_plot[(df_plot.exclude == False)],
                                  md[0]['coating_ab'],
                                  md[0]['prot'],
                                  md[0]['ab2'],
                                  md[0]['coating_ab_units'],
                                  md[0]['prot_units'],
                                  md[0]['ab2_units'],
                                  prot_conc,
                                  md[0]['name'])
            if p:
                plots.append(p)
    
    script, div = components(plots)
    
    html = flask.render_template(
        'layouts/index.html',
        plot_script=script, plot_div=div,
        wells=wells,
        max_value=max_value,
        md=md[0],
        plate_file=plate_filename,
        plate_dir=plate_dirname,
        mean=True,
    )
    return encode_utf8(html)


@app.route("/view", methods=['GET', 'POST'])
def view():
    
    # FORM VARS
    excl = request.form.getlist('exclude')
    submit = request.form.get('submit')
    
    plate_filename = request.args.get('plate_file')
    
    plate_dir = request.args.get('plate_dir')
    plate_dirname = plate_dir
    plate_dir = plate_dir.replace('\\','').replace('/','')

    if plate_dir:
        plate_dir = '%s/%s' % (APP_DATA, plate_dir)

    plate_file = '%s/%s' % (plate_dir, plate_filename)
    
    # METADATA.csv
    
    md = read_plate_file_to_csv_metadata(plate_dir,
                                         plate_filename)
    
    prot_concentration_high = float(md[0]['prot_max'])
    coating_ab_max = float(md[0]['coating_ab_max'])  
    ab2_max = float(md[0]['ab2_max'])
    
    # DF PROCESSING 
    df = process_plate_to_df(plate_file,
                    prot_concentration_high,
                    coating_ab_max,
                    ab2_max)

    max_value = int(df['value'].max())
    

    # EXCLUSIONS
    if submit == 'true':
        write_csv_exclude(plate_file, excl)
    else:
        excl = get_csv_exclude('%s.exc' % plate_file)
    
    df = process_exclusions(df, excl)
    
    # to pass through to plate (rowwise)
    # reset index, then transform, to dict
    wells = get_wells_dict_for_template(df)

    # exclude wells for graph
    df_plot = df[:80]
    get_ab2_multiplier(df, ab2_max)
    
    plots = list()
    for prot_conc in df.sort_values('prot').prot.unique():
        
        if not df_plot.empty:
            p = get_plot_for_prot(df_plot[(df_plot.exclude == False)],
                                  md[0]['coating_ab'],
                                  md[0]['prot'],
                                  md[0]['ab2'],
                                  md[0]['coating_ab_units'],
                                  md[0]['prot_units'],
                                  md[0]['ab2_units'],
                                  prot_conc,
                                  md[0]['name'])
            if p:
                plots.append(p)
    
    script, div = components(plots)
    
    html = flask.render_template(
        'layouts/index.html',
        plot_script=script, plot_div=div,
        wells=wells,
        max_value=max_value,
        md=md[0],
        plate_file=plate_filename,
        plate_dir=plate_dirname,
        mean=False,
    )
    return encode_utf8(html)

@app.route("/")
def index():

    html = flask.render_template(
        'layouts/reports.html',
        reports=get_index(APP_DATA)
    )
    return encode_utf8(html)


@app.route('/<dirname>')
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

@app.route('/upload', methods=['GET','POST'])
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
                       request.form.get('coating_ab'),
                       request.form.get('prot'),
                       request.form.get('ab2'),
                       request.form.get('coating_ab_units'),
                       request.form.get('prot_units'),
                       request.form.get('ab2_units'),
                       float(request.form.get('coating_ab_max')),
                       float(request.form.get('prot_max')),
                       float(request.form.get('ab2_max')),
                       filenames,
                       request.form.get('name'))
        
        return redirect(url_for('index_dirname', dirname=os.path.basename(save_dir)))

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
    app.run(host='0.0.0.0', port=5918)
