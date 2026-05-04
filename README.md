# Static PHP Webshell Detection

## Overview

This project implements a static PHP webshell detection pipeline using source-code preprocessing, tokenization, feature extraction, and model evaluation.

The main goal is to classify PHP files as either benign or webshell based on static source code analysis, without executing the files.

The project compares multiple model approaches:

- TF-IDF + Support Vector Machine
- TF-IDF + Random Forest
- TF-IDF + Multilayer Perceptron
- TextCNN
- CodeBERT

It also includes evaluation on obfuscated PHP webshell samples to test how well the detection pipeline performs under more challenging conditions.

## Problem Statement

PHP webshells are malicious scripts that can be uploaded to compromised web servers to provide unauthorized remote access.

Traditional detection approaches often rely on signatures or manually written rules. These methods can be limited when attackers modify or obfuscate the source code.

This project explores whether static source code representation and machine learning / deep learning models can help detect PHP webshells more effectively.

## Project Objectives

The objectives of this project are:

1. Build a static analysis pipeline for PHP source code.
2. Clean and preprocess PHP files for model training.
3. Convert source code into machine-readable features.
4. Compare traditional machine learning, deep learning, and transformer-based models.
5. Evaluate model performance on normal and obfuscated samples.
6. Practice building a reproducible machine learning pipeline for a cybersecurity use case.

## Pipeline Overview

The project follows the pipeline below:

```text
PHP Source Files
        |
        v
Data Collection
        |
        v
Data Cleaning and Deduplication
        |
        v
Source Code Preprocessing
        |
        v
Tokenization / Feature Extraction
        |
        v
Model Training
        |
        v
Model Evaluation
        |
        v
Robustness Testing on Obfuscated Samples
```

## Methodology

### 1. Data Cleaning

The data cleaning process removes low-quality or duplicated samples before model training.

Examples of cleaning steps include:

- Removing duplicate files
- Filtering very short or invalid PHP files
- Removing suspiciously mislabeled samples
- Standardizing the input format for downstream processing

### 2. Source Code Representation

PHP source code is converted into token-based representations.

The project supports:

- Regex-based tokenization
- Source-code token processing
- TF-IDF feature extraction
- Sequence-based representation for deep learning models
- CodeBERT tokenization for transformer-based modeling

### 3. Model Training

The project compares several models with different levels of complexity.

| Model | Type | Description |
|---|---|---|
| TF-IDF + SVM | Traditional ML | Linear model for high-dimensional sparse text features |
| TF-IDF + Random Forest | Traditional ML | Tree-based model for non-linear feature interactions |
| TF-IDF + MLP | Neural Network | Feedforward neural network trained on TF-IDF features |
| TextCNN | Deep Learning | CNN-based model for local token sequence patterns |
| CodeBERT | Transformer | Pre-trained code model for contextual source-code representation |

### 4. Evaluation

The models are evaluated using common classification metrics:

- Accuracy
- Precision
- Recall
- F1-score
- AUC
- False Negative Rate
- False Positive Rate

In this security-related task, recall and false negative rate are especially important because missing a webshell can be more serious than producing a false alert.

## Results Summary

The project evaluated multiple models under the same experimental setting.

In the experiment, the TF-IDF + MLP model was selected as the final balanced model because it provided strong performance while remaining lightweight and practical to run.

### Held-Out Test Result

| Model | F1-score | AUC | False Negative Rate | False Positive Rate |
|---|---:|---:|---:|---:|
| TF-IDF + MLP | 0.9875 | 0.9993 | 0.2% | 1.7% |

### Obfuscated Webshell Stress Test

| Class | Precision | Recall | F1-score | Support |
|---|---:|---:|---:|---:|
| Benign | 1.00 | 0.98 | 0.99 | 656 |
| Webshell (Obfuscated) | 0.87 | 0.99 | 0.93 | 76 |
| Overall | 0.98 | 0.98 | 0.98 | 732 |

These results suggest that static source-code representation can still capture useful detection signals even when some webshell samples are obfuscated.

However, the robustness result should be interpreted within the scope of the current dataset and should not be treated as a complete guarantee against all possible obfuscation techniques.

## Dataset and Safety Notice

This repository does not include raw malicious PHP samples, generated webshells, or collected datasets.

This project is intended for educational and defensive security research purposes only.

Important notes:

- Do not execute collected PHP samples.
- Do not use this project to create or deploy webshells.
- Dataset collection should only be performed in an isolated and authorized research environment.
- Any use of public security datasets should follow their original licenses and usage terms.
- The purpose of this project is detection and analysis, not offensive usage.

## Repository Structure

```text
php-webshell-static-detector/
├── README.md
├── requirements.txt
├── config.py
├── run.py
├── diagnose.py
├── data/
│   ├── __init__.py
│   ├── collector.py
│   ├── cleaner.py
│   └── splitter.py
├── features/
│   ├── __init__.py
│   └── extractor.py
├── detector/
│   ├── __init__.py
│   ├── base_model.py
│   ├── model.py
│   ├── sklearn_models.py
│   ├── textcnn.py
│   ├── codebert.py
│   ├── trainer.py
│   └── evaluator.py
├── img/
│   ├── alpha.PNG
│   └── beta.PNG
└── .gitignore
```

## How to Run

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/php-webshell-static-detector.git
cd php-webshell-static-detector
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate the virtual environment.

For Windows PowerShell:

```bash
venv\Scripts\Activate.ps1
```

For macOS or Linux:

```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Review Configuration

Before running the pipeline, review:

```text
config.py
```

Make sure dataset paths and optional model settings are appropriate for your local environment.

For safety, webshell generation or external dataset collection should not be enabled unless you are working in an isolated and authorized research environment.

### 5. Run the Pipeline

```bash
python run.py
```

## Important Usage Notes

This repository is designed as a portfolio and research project.

The code is provided to demonstrate:

- Static code preprocessing
- Feature extraction
- Model comparison
- Evaluation methodology
- Defensive security awareness

It is not intended to provide a ready-to-deploy production security product.

## Key Concepts Practiced

Through this project, I practiced:

- Python project organization
- Data collection pipeline design
- Data cleaning and deduplication
- Source-code preprocessing
- Tokenization for PHP code
- TF-IDF feature extraction
- Traditional machine learning model training
- Deep learning model implementation with TextCNN
- Transformer-based modeling with CodeBERT
- Model evaluation using classification metrics
- Robustness testing on obfuscated samples
- Defensive cybersecurity research documentation

## Limitations

This project has several limitations:

- Raw datasets are not included in this repository for safety reasons.
- The pipeline is based on static analysis only and does not analyze runtime behavior.
- The obfuscated stress-test set is limited in size.
- Results may vary depending on dataset quality and collection sources.
- This project is not a production-grade malware detection system.

## Future Improvements

Possible improvements include:

- Add a clearer command-line interface for training and evaluation.
- Improve support for AST-based PHP tokenization.
- Add more structured experiment logging.
- Add model explainability using feature importance or SHAP.
- Expand robustness evaluation with more diverse obfuscation techniques.
- Add unit tests for preprocessing and feature extraction modules.
- Add a small safe sample dataset with synthetic non-malicious examples.
- Improve documentation for each pipeline module.

## Ethical Use

This project is strictly for educational, academic, and defensive security research purposes.

Do not use this project to:

- Deploy webshells
- Generate unauthorized malicious payloads
- Scan systems without permission
- Handle malware samples outside a safe environment

Any real-world testing should only be performed on systems and datasets that you own or are explicitly authorized to analyze.

## Author

**Kathy**

Aspiring Data Engineer with interests in Python, machine learning pipelines, data preprocessing, model evaluation, and defensive cybersecurity analytics.