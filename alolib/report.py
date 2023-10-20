# import pandas as pd
# import numpy as np
# import matplotlib.pyplot as plt
# import seaborn as sns

# import json

# from glob import glob

# import sys

# import json
# import pickle

# from PIL import Image
# import yaml

# def show_graph(algo, df, g_key, time, x_col, model_name='', title='', range_dict=None, ylim=None, train_range_dict=None, xlim=None, groupby_key='extracted_host'):
#     """ Description
#         -----------
#             Show time-series signals with anomaly detection and missing data.
#         Parameters
#         -----------
#             df (dataframe): time-series signal dataframe with time, x_column, groupby key
#             g_key(str): groupby key
#             time(str): time column name
#             x_col(str): time-series signal's column name
#             model_name(str): HPO selected AD model's name
#             title(str): Add message to graph's title
#             range_dict(dict in list): ignore(currently not used)
#             ylim(tuple): y axis limits
#             train_range_dict(dict in list): when showing inference graph, you can add training range of y-axis(Only used for inference)
#             xlim(tuple): x axis limits
#             groupby_key(str): groupby key's column name
#         Return
#         -----------
#             None, Show graph and print Anomaly ratio
#         Example
#         -----------
#             show_graph(df, 'SplunkEdgeHub-d2a3', 'time', 'temperature', model_name='rrcf', title='Training')
#     """
#     df_temp = df.loc[df[groupby_key]==g_key]
#     if '3a6b' in g_key:
#         title = f'%s / %s / %s / {algo}_%s' % (title, 'Lab:%s' % g_key, x_col, model_name)
#     else:
#         title = f'%s / %s / %s / {algo}_%s' % (title, 'A1:%s' % g_key, x_col, model_name)
    
#     plt.figure(figsize=(12, 4))
#     plt.title(title)
            
#     if 'anomaly_detection' in df_temp.columns:
#         for v in df_temp.loc[df_temp.anomaly_detection, time]:
#             plt.axvline(v, c='C1', alpha=0.3)
#         plt.plot([], [],c='C1', label='Anomaly')
#     sns.lineplot(data=df_temp, x=time, y=x_col)
    
#     label = 'missing'
#     for val in df.loc[df[x_col].isna(), time]:
#         plt.axvline(val, c='C3', ls=':', label=label)
#         label = ''
#     if range_dict is not None:
#         alpha = 0.2
#         for r_dict in range_dict:
#             time_st = r_dict['time_st']
#             time_ed = r_dict['time_ed']
#             time_key = r_dict['time_key']
# #             plt.axvline(time_st, c='gray', ls=':', label=time_key)
# #             plt.axvline(time_ed, c='gray', ls=':')
#             if ylim is None:
#                 axes = plt.gca()
#                 ymin, ymax = axes.get_ylim()
#             else:
#                 ymin = ylim[0]
#                 ymax = ylim[1]
#             plt.fill_betweenx(y=[ymax, ymin], x1=[time_st, time_st], x2=[time_ed, time_ed], color='gray', alpha=alpha, label=time_key)
#             alpha += 0.2
#             plt.ylim(ymin, ymax)
            
#     if train_range_dict is not None:
#         alpha = 0.2
#         for r_dict in train_range_dict:
#             y_st = r_dict['y_st']
#             y_ed = r_dict['y_ed']
#             y_key = r_dict['y_key']
            
# #             plt.axvline(time_st, c='gray', ls=':', label=time_key)
# #             plt.axvline(time_ed, c='gray', ls=':')
#             if xlim is None:
#                 axes = plt.gca()
#                 xmin, xmax = axes.get_xlim()
#             else:
#                 xmin = xlim[0]
#                 xmax = xlim[1]
#             plt.axhline(y_st, ls=':', color='black', alpha=alpha)
#             plt.axhline(y_ed, ls=':', color='black', alpha=alpha, label=y_key)
# #             plt.fill_between(x=[xmax, xmin], y1=[y_st, y_st], y2=[y_ed, y_ed], color='gray', alpha=alpha, label=y_key)
#             alpha += 0.2
#             plt.xlim(xmin, xmax)
#     if ylim is not None:
#         ymin = ylim[0]
#         ymax = ylim[1]
        
#         plt.ylim(ymin, ymax)
#     plt.legend()
#     plt.grid(c='lightgray')
#     plt.show()
#     if 'anomaly_detection' in df.columns:
#         print('Anomaly ratio: %.2f%%' % (df.loc[df[groupby_key]==g_key, 'anomaly_detection'].sum() / len(df) * 100))

    
# # 실험을 통해 imputation 조건이 정해진 경우 변경
# def imp_condition(idx):
#     return idx
                     
# def gen_missing_ratio(df, df_viz, x_col, time_key, time_window):
    
#     fig = plt.figure(figsize=(15, 20))
#     ax = fig.add_subplot(411)
#     plt.title('[Missing ratio] time window:%d' % time_window)
#     sns.barplot(data=df_viz, x='time', y='nan_ratio', ax=ax)
#     plt.xticks(rotation=90)
#     plt.grid(c='lightgray')
    
#     ax = fig.add_subplot(412)
#     plt.title('[Number of missing data] time window:%d' % time_window)
#     sns.barplot(data=df_viz, x='time', y='nan', ax=ax)
    
#     plt.xticks(rotation=90)
#     ymax = len(df_viz) + 1
#     plt.ylim(0, ymax)
#     plt.grid(c='lightgray')
    
#     ax = fig.add_subplot(413)
#     plt.title('[Number of imputation data] time window:%d' % time_window)
#     sns.barplot(data=df_viz, x='time', y='imputation', ax=ax)
#     plt.xticks(rotation=90)
#     plt.ylim(0, ymax)
#     plt.grid(c='lightgray')
#     mean_list = df_viz['mean'].values.tolist()
#     std_list = df_viz['std'].values.tolist()
#     n_sigma = 1
#     cond1 = mean_list[1:] > (np.array(mean_list) + n_sigma * np.array(std_list))[:-1]
#     cond2 = mean_list[1:] < (np.array(mean_list) - n_sigma * np.array(std_list))[:-1]
#     cond = cond1 + cond2

#     ax = fig.add_subplot(414)
#     plt.title('Data distribution shift check')
#     sns.lineplot(data=df, x=time_key, y=x_col, ax=ax)
#     plt.xlim(df_viz['time'].iloc[0], df_viz['time'].iloc[-1])
#     label = 'distribution shift'
#     for val in np.array(df_viz['time'].iloc[1:])[cond]:
        
#         plt.axvline(val, ls=':', c='C1', label=label)
#         label = ''
#     if not bool(label):
#         plt.legend()
#     plt.grid(c='lightgray')
#     plt.tight_layout()
#     plt.show()

# def gen_df_viz(df, time_window, x_col, time_key):
#     num_total = len(df)
#     n_window = int(num_total/time_window) + 1
#     nan_list = []
#     nan_ratio_list = []
#     time_list = []
#     mean_list = []
#     std_list = []
#     imputation_list = []

#     for i in range(n_window):
#         try:
#             df_temp = df.iloc[time_window*i:time_window*(i+1)]
#             num_df = len(df_temp)
#             num_nan = df_temp[x_col].isna().sum()
#             if num_nan != 0:
#                 imp_cand_idxs = df_temp.index[df_temp['imp_mask']==1]
#                 imp_cand_idxs_remain = imp_condition(imp_cand_idxs)
#                 imputation_list.append(len(imp_cand_idxs_remain))
#             else:
#                 imputation_list.append(0)

#             time_list.append(df_temp[time_key].iloc[0])
#             nan_list.append(num_nan)
#             mean_list.append(df_temp[x_col].mean())
#             std_list.append(df_temp[x_col].std())
#             nan_ratio_list.append((1 - num_nan/num_df) * 100)
#         except:
#             pass
#     df[time_key] = [df.iloc[int(i / time_window) * time_window][time_key] for i in range(len(df))]

#     df_viz = pd.DataFrame([time_list, nan_ratio_list, nan_list, imputation_list, mean_list, std_list], index=['time', 'nan_ratio', 'nan', 'imputation', 'mean', 'std']).T
#     return df_viz