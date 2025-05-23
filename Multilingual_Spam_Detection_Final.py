# -*- coding: utf-8 -*-
"""Untitled0.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1oXAXY7LGH0dqztHTZ5-ELVrZnW3p-_XF
"""

import pandas as pd
import numpy as np
import re
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, roc_curve
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from transformers import DistilBertTokenizer, DistilBertModel
import torch
import shap
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import nltk
import os

# Download NLTK data
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('punkt_tab')

# Load dataset
df = pd.read_csv('data-augmented.csv', sep=",", header=0)
# Check missing values
df.isnull().sum()

df = df.dropna()

df.isnull().sum()

# Check spam and ham values
df['labels'].value_counts().plot(kind='bar')

# Initialize empty lists for each language
processed_data = []

# Languages to process
languages = ['text', 'text_es', 'text_ar', 'text_ru', 'text_pt']

# Define stopwords for each language
stopwords_ar = set(open('arabic.txt').read().splitlines())
stopwords_es = set(open('spanish.txt').read().splitlines())
stopwords_ru = set(open('russian.txt').read().splitlines())
stopwords_pt = set(open('portuguese.txt').read().splitlines())

# Create preprocessing function (modified to handle multiple languages)
def preprocess_text(text, language='english'):
    if pd.isna(text):  # Handle NaN values
        return ''

    # Convert to lowercase
    text = str(text).lower()

    # Language-specific preprocessing
    if language == 'english':
        # Remove special characters (keep apostrophes for contractions)
        text = re.sub(r"[^a-zA-Z\s']", '', text)
        stop_words = set(stopwords.words('english'))
    elif language == 'ar':
        # Arabic processing
        text = re.sub(r"[^\u0600-\u06FF\s]", '', text)  # Keep Arabic letters and spaces
        stop_words = stopwords_ar
    elif language == 'es':
        # Spanish processing
        text = re.sub(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ\s]", '', text)
        stop_words = stopwords_es
    elif language == 'ru':
        # Russian processing
        text = re.sub(r"[^а-яА-ЯёЁ\s]", '', text)
        stop_words = stopwords_ru
    elif language == 'pt':
        # Portuguese processing
        text = re.sub(r"[^a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ\s]", '', text)
        stop_words = stopwords_pt
    else:
        # Default case (shouldn't happen with our languages list)
        text = re.sub(r"[^\w\s]", '', text)
        stop_words = set()

    # Tokenize the text
    tokens = word_tokenize(text)

    # Remove stopwords
    filtered_tokens = [word for word in tokens if word not in stop_words]

    # Join the tokens back into a single string
    preprocessed_text = ' '.join(filtered_tokens)

    return preprocessed_text

# Process data for each language
for index, row in df.iterrows():
    label = row['labels']

    for lang in languages:
        text = row[lang]
        lang_code = 'english' if lang == 'text' else lang.split('_')[-1]
        processed_text = preprocess_text(text, lang_code)
        processed_data.append([label, lang, processed_text])

# Create DataFrame from processed data
processed_df = pd.DataFrame(processed_data, columns=["labels", "language", "text"])

# Encode labels
processed_df['labels'] = processed_df['labels'].map({'ham': 0, 'spam': 1})

# Initialize DistilBERT tokenizer and model
tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-multilingual-cased')
model = DistilBertModel.from_pretrained('distilbert-base-multilingual-cased')
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)

# Function to get embeddings with batching
def get_embeddings(texts, batch_size=16):
    embeddings = []
    model.eval()

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        inputs = tokenizer(batch, return_tensors='pt', padding=True, truncation=True, max_length=128).to(device)

        with torch.no_grad():
            outputs = model(**inputs)

        batch_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        embeddings.append(batch_embeddings)

    return np.vstack(embeddings)

# Normalize embeddings to [0,1] range for Naive Bayes
def normalize_embeddings(embeddings):
    min_val = embeddings.min()
    max_val = embeddings.max()
    return (embeddings - min_val) / (max_val - min_val)

# Process each language
language_groups = processed_df.groupby('language')
results = {}

for lang, group in language_groups:
    print(f"\nProcessing language: {lang}")

    # Get embeddings
    texts = group['text'].tolist()
    print(f"Generating embeddings for {len(texts)} samples...")
    embeddings = get_embeddings(texts)

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        embeddings, group['labels'], test_size=0.2, random_state=42)
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.25, random_state=42)

    print(f"Train: {X_train.shape[0]}, Val: {X_val.shape[0]}, Test: {X_test.shape[0]}")

    # Initialize models - using GaussianNB instead of MultinomialNB
    models = {
        'KNN': KNeighborsClassifier(),
        'Naive Bayes': GaussianNB(),
        'SVM': SVC(probability=True, kernel='linear'),
        'Random Forest': RandomForestClassifier(n_estimators=100),
        'Decision Tree': DecisionTreeClassifier(max_depth=5),
        'Logistic Regression': LogisticRegression(max_iter=1000),
        'XGBoost': XGBClassifier()
    }

    # Train and evaluate
    lang_results = {}
    plt.figure(figsize=(10, 8))

    for name, clf in models.items():
        print(f"Training {name}...")

        # Normalize data for Naive Bayes
        if name == 'Naive Bayes':
            X_train_norm = normalize_embeddings(X_train)
            X_test_norm = normalize_embeddings(X_test)
            clf.fit(X_train_norm, y_train)
            y_proba = clf.predict_proba(X_test_norm)[:, 1]
            y_pred = clf.predict(X_test_norm)
        else:
            clf.fit(X_train, y_train)
            y_proba = clf.predict_proba(X_test)[:, 1] if hasattr(clf, 'predict_proba') else clf.decision_function(X_test)
            y_pred = clf.predict(X_test)

        # Metrics
        lang_results[name] = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred),
            'recall': recall_score(y_test, y_pred),
            'f1': f1_score(y_test, y_pred),
            'roc_auc': roc_auc_score(y_test, y_proba)
        }

        # ROC curve
        fpr, tpr, _ = roc_curve(y_test, y_proba)
        plt.plot(fpr, tpr, label=f'{name} (AUC = {lang_results[name]["roc_auc"]:.2f})')

    # Plot ROC
    plt.title(f'ROC Curves - {lang}')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.legend()
    plt.show()

    results[lang] = lang_results

# Combined analysis
print("\nProcessing combined languages...")
all_texts = processed_df['text'].tolist()
all_labels = processed_df['labels'].values

print("Generating embeddings for all languages...")
all_embeddings = get_embeddings(all_texts)

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    all_embeddings, all_labels, test_size=0.2, random_state=42)
X_train, X_val, y_train, y_val = train_test_split(
    X_train, y_train, test_size=0.25, random_state=42)

print(f"Train: {X_train.shape[0]}, Val: {X_val.shape[0]}, Test: {X_test.shape[0]}")

# Train and evaluate
combined_results = {}
plt.figure(figsize=(10, 8))

for name, clf in models.items():
    print(f"Training {name} on combined data...")

    if name == 'Naive Bayes':
        X_train_norm = normalize_embeddings(X_train)
        X_test_norm = normalize_embeddings(X_test)
        clf.fit(X_train_norm, y_train)
        y_proba = clf.predict_proba(X_test_norm)[:, 1]
        y_pred = clf.predict(X_test_norm)
    else:
        clf.fit(X_train, y_train)
        y_proba = clf.predict_proba(X_test)[:, 1] if hasattr(clf, 'predict_proba') else clf.decision_function(X_test)
        y_pred = clf.predict(X_test)

    # Metrics
    combined_results[name] = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred),
        'recall': recall_score(y_test, y_pred),
        'f1': f1_score(y_test, y_pred),
        'roc_auc': roc_auc_score(y_test, y_proba)
    }

    # ROC curve
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    plt.plot(fpr, tpr, label=f'{name} (AUC = {combined_results[name]["roc_auc"]:.2f})')

# Plot ROC
plt.title('ROC Curves - Combined Languages')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.legend()
plt.show()

# Display results
def print_results(result_dict, title):
    print(f"\n{title}")
    print("-" * 60)
    df = pd.DataFrame(result_dict).T
    print(df.round(4))

for lang, res in results.items():
    print_results(res, f"Results for {lang}")

print_results(combined_results, "Results for Combined Languages")

# SHAP analysis (for XGBoost on combined data)
try:
    print("\nGenerating SHAP explanation...")
    explainer = shap.Explainer(models['XGBoost'], X_train[:100])  # Use subset for performance
    shap_values = explainer(X_test[:100])

    shap.summary_plot(shap_values, X_test[:100], show=False)
    plt.title('SHAP Summary - XGBoost (Combined Languages)')
    plt.show()
except Exception as e:
    print(f"\nSHAP analysis failed: {str(e)}")
