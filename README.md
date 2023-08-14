# Stack Overflow for Teams Interactions (so4t_interactions)
An API script for Stack Overflow for Teams that creates a chord diagram, demonstrating how teams are interacting within the product.

All data obtained via the API is handled locally on the device from which the script is run. The script does not transmit data to other parties, such as Stack Overflow. All of the API calls performed are read only, so there is no risk of editing or adding content on your Stack Overflow for Teams instance.

This script is offered with no formal support from Stack Overflow. If you run into issues using the script, please [open an issue](https://github.com/jklick-so/so4t_interactions/issues) and/or reach out to the person who provided it to you. You are also welcome to edit the script to suit your needs.

## Requirements
* Stack Overflow Enterprise
* Python 3.x ([download](https://www.python.org/downloads/))
* Operating system: Linux, MacOS, or Windows

## Setup

[Download](https://github.com/jklick-so/so4t_interactions/archive/refs/heads/display_name.zip) and unpack the contents of this repository

**Installing Dependencies**

* Open a terminal window (or, for Windows, a command prompt)
* Navigate to the directory where you unpacked the files
* Install the dependencies: `pip3 install -r requirements.txt`

**API Authentication**

For Stack Overflow Enteprise, documentation for creating a key can be found within your instance, at this url: `https://[your_site]/api/docs/authentication`


## Usage
In a terminal window, navigate to the directory where you unpacked the script. 
Run the script using the following format, replacing the URL, token, and/or key with your own:
`python3 so4t_interactions.py --url "https://SUBDOMAIN.stackenterprise.co" --key "YOUR_KEY" --token "YOUR_TOKEN"`

The script can take several minutes to run, particularly as it gathers data via the API. As it runs, it will continue to update the terminal window with the tasks it's performing.

When the script completes, it will indicate the chord diagram has been created, and will provide the path to the file. The file will be saved in the same directory as the script.

