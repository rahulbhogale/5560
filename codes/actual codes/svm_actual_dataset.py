# -*- coding: utf-8 -*-
"""svm.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1g_2V2K-45oUxOg1XvYhCIdUm_YvjCU-Y

###Import all the Libraries
"""

from pyspark.sql.types import *
from pyspark.sql.functions import *
from pyspark.sql.functions import col, when, max

from pyspark.ml import Pipeline

from pyspark.ml.classification import LinearSVC

from pyspark.ml.feature import VectorAssembler, StringIndexer, VectorIndexer, MinMaxScaler
from pyspark.ml.tuning import ParamGridBuilder, TrainValidationSplit, CrossValidator
from pyspark.ml.evaluation import MulticlassClassificationEvaluator, BinaryClassificationEvaluator

from pyspark.context import SparkContext
from pyspark.sql.session import SparkSession

"""###Create a Spark-Submit Session"""

PYSPARK_CLI = True # conditional statement to run only at shell
if PYSPARK_CLI:
    sc = SparkContext.getOrCreate()
    spark = SparkSession(sc)

# Limit the log
spark.sparkContext.setLogLevel("WARN")

"""###Load the sample dataset from DBFS"""

# Oracle BDCE
csv = spark.read.csv('/user/agupta25/project/benefit.csv', inferSchema=True, header=True)
csv.show()

"""### Prepare the Data"""

df = csv.select('BusinessYear', 'StateCode', 'IssuerId', 'SourceName', 'IsEHB', 'QuantLimitOnSvc', 'Exclusions', 'EHBVarReason',col("IsCovered").alias("label"))

df.show()

df.printSchema()

"""###count the null values from prediction col"""

from pyspark.sql.functions import col, sum

# assuming that `df` is a Spark DataFrame and `label` is a column in `df`
null_count = df.select(sum(col("label").isNull().cast("integer"))).collect()[0][0]
print(null_count)

"""###Replace null or whitespace values with None. Later drop the values."""

from pyspark.sql.functions import when, col

# Replace empty strings or whitespace with null values
df = df.withColumn('label', when(col('label').isin('', ' '), None).otherwise(col('label')))

# Drop null values from label column
df = df.dropna(subset=['label'])
df.show()

"""###Take Max of all the other columns in dataset having null values"""

df.agg({'IsEHB': 'max','QuantLimitOnSvc':'max','Exclusions':'max','EHBVarReason':'max'}).collect()

"""###Populating the aggregated values of other columns inplace of null values"""

df = df.fillna({
    "BusinessYear": 0,
    "StateCode": "",
    "IssuerId": 0,
    "SourceName": "",
    "IsEHB": "Yes",
    "QuantLimitOnSvc": "Yes",
    "Exclusions": "in vitro fertilization and artificial insemination",
    "EHBVarReason": "Using Alternate Benchmark",
    "label": ""
})

df.show()

"""###Convert the label into 0 and 1 for classification modelling and prediction."""

df = df.withColumn("label", when(df["label"] == "Covered", 1).otherwise(0))
df.show()

"""###Shows the summary of dataset"""

df.describe().show()

"""###Shows the existing null values in dataset"""

df.select([count(when(isnull(c), c)).alias(c) for c in df.columns]).show()

"""### Split the Data for training & testing"""

splits = df.randomSplit([0.7, 0.3])
train = splits[0]
test = splits[1].withColumnRenamed("label", "trueLabel")
train_rows = train.count()
test_rows = test.count()
print("Training Rows:", train_rows, " Testing Rows:", test_rows)

"""### Define the Pipeline
A predictive model often requires multiple stages of feature preparation. For example, it is common when using some algorithms to distingish between continuous features (which have a calculable numeric value) and categorical features (which are numeric representations of discrete categories). It is also common to *normalize* continuous numeric features to use a common scale (for example, by scaling all numbers to a proportinal decimal value between 0 and 1).

A pipeline consists of a a series of *transformer* and *estimator* stages that typically prepare a DataFrame for
modeling and then train a predictive model. In this case, you will create a pipeline with seven stages:
- A **StringIndexer** estimator that converts string values to indexes for categorical features
- A **VectorAssembler** that combines categorical features into a single vector
- A **VectorIndexer** that creates indexes for a vector of categorical features
- A **VectorAssembler** that creates a vector of continuous numeric features
- A **MinMaxScaler** that normalizes continuous numeric features
- A **VectorAssembler** that creates a vector of categorical and continuous features
- A **DecisionTreeClassifier** that trains a classification model.
"""

strIdx_SC = StringIndexer(inputCol = "StateCode", outputCol = "SC",handleInvalid='keep')
strIdx_SN = StringIndexer(inputCol = "SourceName", outputCol = "SN",handleInvalid='keep')
strIdx_EHB = StringIndexer(inputCol = "IsEHB", outputCol = "EHB",handleInvalid='keep')
strIdx_QL = StringIndexer(inputCol = "QuantLimitOnSvc", outputCol = "QL",handleInvalid='keep')
strIdx_EX = StringIndexer(inputCol = "Exclusions", outputCol = "EX",handleInvalid='keep')
strIdx_EHBVR = StringIndexer(inputCol = "EHBVarReason", outputCol = "EHBVR",handleInvalid='keep')


# the following columns are categorical number such as ID so that it should be Category features
catVect = VectorAssembler(inputCols = ["SC", "BusinessYear", "IssuerId", "SN", "EHB","QL","EHBVR"], outputCol="catFeatures")
catIdx = VectorIndexer(inputCol = catVect.getOutputCol(), outputCol = "idxCatFeatures", handleInvalid="skip")

"""###Shows the feature extraction count of cat features"""

# Fit the string indexers on the input data
strIdx_SC_model = strIdx_SC.fit(df)
strIdx_SN_model = strIdx_SN.fit(df)
strIdx_EHB_model = strIdx_EHB.fit(df)
strIdx_QL_model = strIdx_QL.fit(df)
strIdx_EX_model = strIdx_EX.fit(df)
strIdx_EHBVR_model = strIdx_EHBVR.fit(df)

# Transform the input data using the fitted string indexers
data_transformed = df
data_transformed = strIdx_SC_model.transform(data_transformed)
data_transformed = strIdx_SN_model.transform(data_transformed)
data_transformed = strIdx_EHB_model.transform(data_transformed)
data_transformed = strIdx_QL_model.transform(data_transformed)
data_transformed = strIdx_EX_model.transform(data_transformed)
data_transformed = strIdx_EHBVR_model.transform(data_transformed)

# Count the number of distinct values in each output column
distinct_counts = {
    "StateCode": data_transformed.select(countDistinct("SC")).collect()[0][0],
    "SourceName": data_transformed.select(countDistinct("SN")).collect()[0][0],
    "IsEHB": data_transformed.select(countDistinct("EHB")).collect()[0][0],
    "QuantLimitOnSvc": data_transformed.select(countDistinct("QL")).collect()[0][0],
    "Exclusions": data_transformed.select(countDistinct("EX")).collect()[0][0],
    "EHBVarReason": data_transformed.select(countDistinct("EHBVR")).collect()[0][0]
}

print(distinct_counts)

# cat feature vector is normalized

minMax = MinMaxScaler(inputCol = catIdx.getOutputCol(), outputCol="normFeatures")

featVect = VectorAssembler(inputCols=["normFeatures"], outputCol="features")

classification_models=["Support Vector Machine (SVM)"]

#creating diff clasf algos for testing accuracy,computing time, precision, recall, ROC, PR
cls_mod=[]


cls_mod.insert(0,LinearSVC(labelCol='label', featuresCol='features'))

# define list of models made from Train Validation Split or Cross Validation
model = []
pipeline = []

# Pipeline process the series of transformation above, which is another transformation
for i in range(0,1):
    pipeline.insert(i,Pipeline(stages=[strIdx_SC,strIdx_SN,strIdx_EHB,strIdx_QL,strIdx_EHBVR, catVect, catIdx,minMax, featVect, cls_mod[i]]))

"""### Tune hyperparameters using ParamGrid"""

paramGrid=[]


    
paramGrid.insert(0,ParamGridBuilder() \
             .addGrid(cls_mod[0].regParam, [0.01, 0.5]) \
             .addGrid(cls_mod[0].maxIter, [1, 5]) \
             .addGrid(cls_mod[0].tol, [1e-4, 1e-3]) \
             .addGrid(cls_mod[0].fitIntercept, [True, False]) \
             .addGrid(cls_mod[0].standardization, [True, False]) \
             .build())

"""### Used CrossValidator for modelling"""

cv=[]
K=3 
for i in range(0,1):
    cv.insert(i, CrossValidator(estimator=pipeline[i], 
                            evaluator=BinaryClassificationEvaluator(), 
                            estimatorParamMaps=paramGrid[i], 
                            numFolds=K))


#cv1 = CrossValidator(estimator=pipeline1, evaluator=BinaryClassificationEvaluator(), estimatorParamMaps=paramGrid1, numFolds=K)
#cv2= CrossValidator(estimator=pipeline2, evaluator=BinaryClassificationEvaluator(), estimatorParamMaps=paramGrid2, numFolds=K)
#cv3 = CrossValidator(estimator=pipeline3, evaluator=BinaryClassificationEvaluator(), estimatorParamMaps=paramGrid3, numFolds=K)
#cv4 = CrossValidator(estimator=pipeline4, evaluator=BinaryClassificationEvaluator(), estimatorParamMaps=paramGrid4, numFolds=K)
#cv5 = CrossValidator(estimator=pipeline5, evaluator=BinaryClassificationEvaluator(), estimatorParamMaps=paramGrid5, numFolds=K)

#cv = TrainValidationSplit(estimator=pipeline, evaluator=BinaryClassificationEvaluator(), estimatorParamMaps=paramGrid, trainRatio=0.8)

"""###Calculating the computing time required to build a model"""

import time

start_time = []
end_time = []
computation_time = []

for i in range(0, 1):
    start_time.insert(i, time.time())
    model.insert(i, cv[i].fit(train))
    # model1 = cv1.fit(train)
    # model2 = cv2.fit(train)
    # model3 = cv3.fit(train)
    # model4 = cv4.fit(train)
    # model5 = cv5.fit(train)
    end_time.insert(i, time.time())
    computation_time.insert(i, (end_time[i] - start_time[i]) / 60.0)
    print("Computation time:",i," ",computation_time[i], "minutes")

"""### Test the Pipeline Model
The model produced by the pipeline is a transformer that will apply all of the stages in the pipeline to a specified DataFrame and apply the trained model to generate predictions. In this case, you will transform the **test** DataFrame using the pipeline to generate label predictions.
"""

prediction =[]
predicted =[]
for i in range(0,1):
    prediction.insert(i,model[i].transform(test))
    prediction[i].show()
    predicted.insert(i,prediction[i].select("features", "prediction","trueLabel"))
    predicted[i].show()
    
    

#LR
#prediction = model.transform(test)
#prediction.show(5)
#predicted = prediction.select("features", "prediction", "probability", "trueLabel")

#predicted.show(10, truncate=False)

#DT
#prediction1 = model1.transform(test)
#predicted1 = prediction1.select("features", "prediction", "probability", "trueLabel")

#predicted1.show(10, truncate=False)

#RF
#prediction2 = model2.transform(test)
#predicted2 = prediction2.select("features", "prediction", "probability", "trueLabel")

#predicted2.show(10, truncate=False)

#SVM
#prediction.insert(5,model[5].transform(test))
#predicted.insert(5, prediction[5].select("features", "prediction", "trueLabel"))

#prediction[5].show(10,truncate=False)
#predicted[5].show(10, truncate=False)

#GBT
#prediction4 = model4.transform(test)
#prediction4.show(5)
#predicted4 = prediction4.select("features", "prediction", "probability", "trueLabel")

#predicted4.show(10, truncate=False)

#FM
#prediction5 = model5.transform(test)
#predicted5 = prediction5.select("features", "prediction", "probability", "trueLabel")

#predicted5.show(10, truncate=False)

"""The resulting DataFrame is produced by applying all of the transformations in the pipline to the test data. The **prediction** column contains the predicted value for the label, and the **trueLabel** column contains the actual known value from the testing data.

### Compute Confusion Matrix Metrics
Classifiers are typically evaluated by creating a *confusion matrix*, which indicates the number of:
- True Positives
- True Negatives
- False Positives
- False Negatives

From these core measures, other evaluation metrics such as *precision* and *recall* can be calculated.
"""

precision=[]
recall=[]
metrics=[]

for i in range(0,1):
    tp = float(predicted[i].filter("prediction== 1.0 AND truelabel == 1").count())
    fp = float(predicted[i].filter("prediction== 1.0 AND truelabel == 0").count())
    tn = float(predicted[i].filter("prediction== 0.0 AND truelabel == 0").count())
    fn = float(predicted[i].filter("prediction==0.0 AND truelabel == 1").count())
    precision.insert(i,tp / (tp + fp))
    recall.insert(i,tp / (tp + fn))
    metrics.insert(i, spark.createDataFrame([
    ("TP", tp),
    ("FP", fp),
    ("TN", tn),
    ("FN", fn),
    ("Precision", tp / (tp + fp)),
    ("Recall", tp / (tp + fn))],["metric", "value"]))
    metrics[i].show()

"""### View the Raw Prediction and Probability
The prediction is based on a raw prediction score that describes a labelled point in a logistic function. This raw prediction is then converted to a predicted label of 0 or 1 based on a probability vector that indicates the confidence for each possible label value (in this case, 0 and 1). The value with the highest confidence is selected as the prediction.
"""

for i in range(0,1):
    prediction[i].select("rawPrediction", "prediction", "trueLabel").show(10, truncate=False)

"""###Calculating metrics such as ROC, PR, Accuracy, F1_score, Precision, Recall"""

evaluator = [None] * 1
ROC = [None] * 1
PR = [None] * 1
ev1 = [None] * 1
accuracy = [None] * 1
f1_score = [None] * 1

for i in range(0, 1):
    evaluator[i] = BinaryClassificationEvaluator(labelCol="trueLabel", rawPredictionCol="rawPrediction")
    ROC[i] = evaluator[i].evaluate(prediction[i], {evaluator[i].metricName: "areaUnderROC"})
    # print("ROC = {0:.3f}".format(auc_roc))

    PR[i] = evaluator[i].evaluate(prediction[i], {evaluator[i].metricName: "areaUnderPR"})
    # print("PR = {0:.3f}".format(auc_pr))

    ev1[i] = MulticlassClassificationEvaluator(labelCol='trueLabel', predictionCol='prediction')
    # accuracy
    accuracy[i] = ev1[i].evaluate(prediction[i], {evaluator[i].metricName: "accuracy"})
    # print("Accuracy = {0:.3f}".format(accuracy))

    # f1 score
    f1_score[i] = ev1[i].evaluate(prediction[i], {evaluator[i].metricName: "f1"})
    # print("F1 = {0:.3f}".format(f1_score))

"""###Comparing all metrics at one place"""

import pandas as pd

results = {
    'Model': classification_models,
    'Computation Time (min)': computation_time,
    'ROC': ROC,
    'PR': PR,
    'Accuracy': accuracy,
    'F1 Score': f1_score,
    'Precision': precision,
    'Recall': recall
}

df_results = pd.DataFrame.from_dict(results)
df_results = df_results.set_index('Model').transpose()

print(df_results)