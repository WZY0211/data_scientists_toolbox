import pandas as pd
import string
import sqlite3

class CreateKaggleSurveyDB:
    def __init__(self):     
        #載入資料
        survey_years = [2020, 2021, 2022]
        df_dict = dict()
        for survey_year in survey_years:
            file_path = f"data/kaggle_survey_{survey_year}_responses.csv"
            df = pd.read_csv(file_path, low_memory=False, skiprows=[1]) # low_memory=False:強制一次性讀完檔案，避免型別判斷錯誤。skiprows=[1]:跳過第2列(不抓問題敘述，只抓欄位名跟資料內容)
            df = df.iloc[:,1:] 
            df_dict[survey_year, "responses"] = df
            df = pd.read_csv(file_path, nrows=1) # 只讀第一列(問題敘述)
            questions_descriptions = df.values.ravel() # df.values：拿到 DataFrame 的值，.ravel()：轉成一維陣列
            questions_descriptions = questions_descriptions[1:]
            df_dict[survey_year, "question_descriptions"] = questions_descriptions
        self.survey_years = survey_years
        self.df_dict = df_dict

    def tidy_2020_2021_data(self, survey_year: int) -> tuple:
        question_indexes, question_types, question_descriptions = [], [], []
        column_names = self.df_dict[survey_year, "responses"].columns # 只取欄位
        descriptions = self.df_dict[survey_year, "question_descriptions"]
        for column_name, question_description in zip(column_names, descriptions):
            column_name_split = column_name.split("_")
            question_description_split = question_description.split(" - ")
            if len(column_name_split) == 1: # 抓取單選題 ex:Q1
                question_index = column_name_split[0]
                question_indexes.append(question_index)
                question_types.append("Multiple choice")
                question_descriptions.append(question_description_split[0])
            else: # 抓取多選題
                if column_name_split[1] in string.ascii_uppercase: # string.ascii_uppercase是所有大寫英文字母的字串。ex:Q26_A
                    question_index = column_name_split[0] + column_name_split[1]
                    question_indexes.append(question_index)
                else:
                    question_index = column_name_split[0] # ex:Q7_Part_1
                    question_indexes.append(question_index)
                question_types.append("Multiple selection")
                question_descriptions.append(question_description_split[0])
        question_df = pd.DataFrame()
        question_df["question_index"] = question_indexes
        question_df["question_type"] = question_types
        question_df["question_description"] = question_descriptions
        question_df["surveyed_in"] = survey_year
        question_df = question_df.groupby(["question_index", "question_type", "question_description", "surveyed_in"]).count().reset_index() # groupby():會把群組欄位變成索引。.count()： 去除重複列。.reset_index()：把這些欄位還原成正常的欄位格式
        response_df = self.df_dict[survey_year, "responses"] # 調整欄位名稱前
        response_df.columns = question_indexes # 調整後欄位名稱
        response_df_reset_index = response_df.reset_index() # 新增索引欄位index
        response_df_melted = pd.melt(response_df_reset_index, id_vars="index", var_name="question_index", value_name="response") # 寬格式 → 長格式
        response_df_melted["responded_in"] = survey_year # 加上年份欄位
        response_df_melted = response_df_melted.rename(columns={"index":"respondent_id"})
        response_df_melted = response_df_melted.dropna().reset_index(drop=True) # 刪除NaN的列。reset_index(drop=True):重新編排索引，並且不要留下原本的索引
        return question_df, response_df_melted
    
    #2022年資料整理
    def tidy_2022_data(self, survey_year: int) -> tuple:
        question_indexes, question_types, question_descriptions = [], [], []
        column_names = self.df_dict[survey_year, "responses"].columns
        descriptions = self.df_dict[survey_year, "question_descriptions"]
        for column_name, question_description in zip(column_names, descriptions):
            column_name_split = column_name.split("_")
            question_description_split = question_description.split("-")
            if len(column_name_split) == 1:
                question_types.append("Multiple choice")
            else:
                question_types.append("Multiple selection")
            question_indexes.append(column_name_split[0])
            question_descriptions.append(question_description_split[0])      
        question_df = pd.DataFrame()
        question_df["question_index"] = question_indexes
        question_df["question_type"] = question_types
        question_df["question_description"] = question_descriptions
        question_df["surveyed_in"] = survey_year
        question_df = question_df.groupby(["question_index", "question_type", "question_description", "surveyed_in"]).count().reset_index()
        response_df = self.df_dict[survey_year, "responses"] 
        response_df.columns = question_indexes 
        response_df_reset_index = response_df.reset_index() 
        response_df_melted = pd.melt(response_df_reset_index, id_vars="index", var_name="question_index", value_name="response") 
        response_df_melted["responded_in"] = survey_year 
        response_df_melted = response_df_melted.rename(columns={"index":"respondent_id"})
        response_df_melted = response_df_melted.dropna().reset_index(drop=True) 
        return question_df, response_df_melted
    
    def create_database(self):
        question_df = pd.DataFrame()
        response_df = pd.DataFrame()
        for survey_year in self.survey_years:
            if survey_year == 2022:
                q_df, r_df = self.tidy_2022_data(survey_year)
            else:
                q_df, r_df = self.tidy_2020_2021_data(survey_year)
            question_df = pd.concat([question_df, q_df], ignore_index=True)
            response_df = pd.concat([response_df, r_df], ignore_index=True)
        connection = sqlite3.connect("data/kaggle_survey.db")
        question_df.to_sql("questions", con=connection, if_exists="replace", index=False)
        response_df.to_sql("responses", con=connection, if_exists="replace", index=False)
        cur = connection.cursor()
        drop_view_sql = """DROP VIEW IF EXISTS aggregated_responses;"""
        create_view_sql = """
        CREATE VIEW aggregated_responses AS
        SELECT questions.surveyed_in,
               questions.question_index,
               questions.question_type,
               questions.question_description,
               responses.response,
               COUNT(responses.respondent_id) AS response_count
        FROM questions 
        JOIN responses 
            ON questions.question_index = responses.question_index 
            AND questions.surveyed_in = responses.responded_in
        GROUP BY questions.surveyed_in, questions.question_index, responses.response
        """
        cur.execute(drop_view_sql)
        cur.execute(create_view_sql)
        connection.close()

create_kaggle_survey_db = CreateKaggleSurveyDB()
create_kaggle_survey_db.create_database()