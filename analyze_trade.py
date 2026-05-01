import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

df = pd.read_csv('Tutorial/prices_round_0_day_-2.csv', sep=';')
tom = df[df['product'] == 'TOMATOES'].copy()
tom['mid_price'] = tom['mid_price'].astype(float)

# 1. Plot raw price
tom.plot(x='timestamp', y='mid_price', title='TOMATOES mid price')
plt.show()

# 2. Check autocorrelation of returns
#    Negative autocorrelation at lag 1 = mean reversion signal
tom['returns'] = tom['mid_price'].diff()
pd.plotting.autocorrelation_plot(tom['returns'].dropna())
plt.title('TOMATOES return autocorrelation')
plt.show()

# 3. Rolling mean as fair value estimate
tom['fair_value'] = tom['mid_price'].rolling(20).mean()
tom['deviation'] = tom['mid_price'] - tom['fair_value']
tom[['mid_price', 'fair_value']].plot(title='Price vs Rolling Fair Value')
plt.show()



trades = pd.read_csv('Tutorial/trades_round_0_day_-2.csv', sep=';')
tom_trades = trades[trades['symbol'] == 'TOMATOES']

# Who is trading and how much?
print(tom_trades.groupby('buyer')['quantity'].sum())
print(tom_trades.groupby('seller')['quantity'].sum())

# Look for bots trading consistent quantities
# Frankfurt Hedgehogs found "Olivia" always traded exactly 15 lots at daily highs/lows
print(tom_trades['quantity'].value_counts())

# Plot trade prices vs time
plt.scatter(tom_trades['timestamp'], tom_trades['price'], 
            c='blue', alpha=0.5, label='trades')
plt.plot(tom['timestamp'], tom['mid_price'], c='orange', label='mid')
plt.legend()
plt.title('TOMATOES trades vs mid price')
plt.show()