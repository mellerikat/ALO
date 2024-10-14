import pandas as pd 
import numpy as np 
import matplotlib.pyplot as plt
import seaborn as sns 

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error ,r2_score ,mean_squared_error

import warnings
warnings.filterwarnings('ignore')
df = pd.read_csv(r"/kaggle/input/advertising-dataset/Advertising.csv").set_index("Unnamed: 0")
df.head()
df.shape
df.describe()
df.info()
def two_plots_num_column(feature):
    
    print(f"the skewness value of {feature} column = {df[feature].skew():.2f}")
    plt.figure(figsize=(10,4))
    
    plt.subplot(1,2,1)
    plt.title('histgram')
    sns.histplot(data=df, x=feature, kde=True)
    plt.axvline(x = df[feature].mean(), c = 'red')
    plt.axvline(x = df[feature].median(), c = 'green')

    plt.subplot(1,2,2)
    plt.title('Boxplot')
    sns.boxplot(y=df[feature])
    plt.show()

two_plots_num_column("Newspaper")
q1, q3 = df['Newspaper'].quantile([0.25, 0.75])
iqr = q3 - q1
lower_bound = q1 - (1.5 * iqr)
upper_bound = q3 + (1.5 * iqr)

df.loc[(df["Newspaper"] < lower_bound) | (df["Newspaper"] > upper_bound), "Newspaper"] = np.nan
df["Newspaper"].fillna(df["Newspaper"].mean(), inplace=True)
            
two_plots_num_column('Sales')
sns.pairplot(df, x_vars=['TV','Radio','Newspaper'], y_vars='Sales', size=5, aspect=0.7);
plt.figure(figsize=(10,10))
sns.pairplot(df)
plt.show();
# check about multicollenarity

from statsmodels.stats.outliers_influence import variance_inflation_factor

columns= df.drop(columns='Sales').columns
# VIF dataframe
vif_data = pd.DataFrame()
vif_data["feature"] = columns
  
# calculating VIF for each feature
vif_data["VIF"] = [variance_inflation_factor(df.drop(columns='Sales').values, i)
                          for i in range(len(columns))]
  
vif_data
X = df.drop(["Sales"],axis=1)
y = df.Sales
# split data

from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(X, y,random_state = 42 ,test_size=0.25)
# build an fit the model 

model = LinearRegression()
model.fit(X_train,y_train)

y_pred= model.predict(X_train)
print("R squared: {}".format(r2_score(y_true=y_train ,y_pred=y_pred)))
print(f"mae : {mean_absolute_error(y_train,y_pred)}")
# create a list of residuals 
residuals = y_train.values - y_pred

mean_residuals = np.mean(residuals)
print("Mean of Residuals {}".format(mean_residuals))
# Plot the histogram of the error terms

fig = plt.figure()
sns.distplot(residuals , bins=20)
fig.suptitle('Error Terms', fontsize = 20)    
plt.xlabel('Errors', fontsize = 18)
plt.show()
plt.scatter(y_pred , residuals)
plt.axhline(y=0,color="red" ,linestyle="--")
plt.show()
import statsmodels.stats.api as sms
from statsmodels.compat import lzip
name = ['f_statistic' , 'p_value' , 'lagrange multipler stat']
test = sms.het_breuschpagan(residuals , X_train)
lzip(name , test)
