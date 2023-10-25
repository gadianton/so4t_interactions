# Standard Python libraries
import re
import time

# Third-party libraries
import requests
from selenium import webdriver
from bs4 import BeautifulSoup


class WebScraper(object):
    
    def __init__(self, url):
    
        if "stackoverflowteams.com" in url: # Stack Overflow Business or Basic
            self.soe = False
        else: # Stack Overflow Enterprise
            self.soe = True
        
        self.base_url = url
        self.s = self.create_session() # create a Requests session with authentication cookies


    def create_session(self):

        s = requests.Session()

        # Configure Chrome driver
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=500,800")
        options.add_experimental_option("excludeSwitches", ['enable-automation'])
        driver = webdriver.Chrome(options=options)

        # Check if URL is valid
        try:
            response = requests.get(self.base_url)
        except requests.exceptions.SSLError:
            print(f"SSL certificate error when trying to access {self.base_url}.")
            print("Please check your URL and try again.")
            raise SystemExit
        except requests.exceptions.ConnectionError:
            print(f"Connection error when trying to access {self.base_url}.")
            print("Please check your URL and try again.")
            raise SystemExit
        
        if response.status_code != 200:
            print(f"Error when trying to access {self.base_url}.")
            print(f"Status code: {response.status_code}")
            print("Please check your URL and try again.")
            raise SystemExit
        
        # Open a Chrome window and log in to the site
        driver.get(self.base_url)
        while True:
            try:
                # if user card is found, login is complete
                driver.find_element("class name", "s-user-card")
                break
            except:
                time.sleep(1)
        
        # pass authentication cookies from Selenium driver to Requests session
        cookies = driver.get_cookies()
        for cookie in cookies:
            s.cookies.set(cookie['name'], cookie['value'])
        driver.close()
        driver.quit()
        
        return s


    def test_session(self):

        soup = self.get_page_soup(f"{self.base_url}/users")
        if soup.find('li', {'role': 'none'}): # this element is only shows if the user is logged in
            return True
        else:
            return False


    def get_user_title_and_team(self, user_id):
        """
        This function goes to the profile page of a user and gets their title and team.
        Requires that the title and department assertions have been configured in the SAML
        settings; otherwise, the title and department will not be displayed on the profile page
        
        Args:
            user_id (int): the user ID of the user whose title and department you want to get

        Returns:
            title (str): the user's title
            team (str): the user's department
        """

        print(f"Getting title and team for user ID {user_id}")
        user_url = f"{self.base_url}/users/{user_id}"
        soup = self.get_page_soup(user_url)
        title_and_team = soup.select_one('div.fs-title.lh-xs')
        try:
            title_and_team = self.strip_html(title_and_team.text)
            team = title_and_team.split(', ')[-1]
            title = title_and_team.split(f", {team}")[0]
        except AttributeError: # if no title/dept returned, `text` method will not work on None
            team = None
            title = None
        except IndexError: # if using old title format
            team = None
            title = title_and_team.text
        
        return title, team
    
        
    def get_page_response(self, url):
        # Uses the Requests session to get page response

        response = self.s.get(url)
        if not response.status_code == 200:
            print(f'Error getting page {url}')
            print(f'Response code: {response.status_code}')
        
        return response
    

    def get_page_soup(self, url):
        # Uses the Requests session to get page response and returns a BeautifulSoup object

        response = self.get_page_response(url)
        try:
            return BeautifulSoup(response.text, 'html.parser')
        except AttributeError:
            return None
        

    def strip_html(self, text):
        # Remove HTML tags and newlines from text
        # There are various scenarios where these characters are present in the text when scraped
        return re.sub('<[^<]+?>', '', text).replace('\n', '').replace('\r', '').strip()
   