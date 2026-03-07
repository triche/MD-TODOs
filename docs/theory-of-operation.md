# Theory of Operation for the MD-TODOs Framework

## Problem Description and Setup

I like to keep all my notes, thoughts, and ideas in one place. I use Markdown files for this because it gives me some amount of formatting, is easy to export to other formats, but yet doesn't require a ton of "code" or overhead which makes it easy to get thoughts out quickly. I also like to record any TODOs or action items that I have in these same Markdown files in line with everything else. Sometimes these TODOs I mark with the word "TODO", other times I simply have an itemized list with the Markdown checkbox, and yet other times the action items are implicit in the notes that I have taken.

The issue is that now I have a distributed set of action items across a multiple files and folders. I have no way to easily see all my TODOs in one place, and it's hard to apply any sort of ranking or prioritization to these TODOs. I also have no way to easily mark these TODOs as done, or to track their progress.

## Desired Solution

I want to use AI to have two jobs, one could think of them as two agents running independently:
1. The first agent is a "TODO Extractor" that scans through all my Markdown files and extracts any TODOs or action items it finds. It should be able to recognize different formats of TODOs, such as those marked with "TODO", those in itemized lists with checkboxes, and even implicit action items in the notes. It should also be able to extract any relevant context around the TODOs, such as the file name, line number, and any surrounding text that might help me understand the TODO better and help me go back and mark it as done. This extractor will watch the folders where I keep the files and update the internal list of TODOs as I add, modify (for example to mark something as complete), or delete files.
2. The second agent is the "TODO Manager" that, given the store of extracted active TODOs, uses AI to apply the "Getting Things Done" (GTD) framework to help me prioritize and manage these TODOs. It should be able to categorize TODOs based on their context, such as work-related, personal, or project-specific. It should also be able to rank TODOs based on their urgency and importance. The TODO Manager should run twice a day, once early in the morning to help me play my day, and once again at lunch to help me knock out urgent and quick tasks in the afternoon and evening. I want these to run as scheduled tasks. Ideally, this agent can also run on Friday afternoon and generate a GTD review of the week, and on Sunday evening to help me plan for the week ahead. The plans it generates should be stored in a Markdown file that I can easily access and refer to throughout the day and week.

## Implementation Careabouts

I will be running this on my local machine, so I want to make sure that the solution is lightweight and doesn't require a lot of resources. I also want to make sure that the solution is secure and doesn't expose any of my data to third parties. I don't care about implementation languages or frameworks. I use a Mac, so I am ok if the automation relies on Mac OS specific features. I can add cross platform support later.

Use OpenAI models for the AI components, but I want to make sure that the solution is designed in a way that allows me to easily swap out the AI provider in the future if I want to. I also want to make sure that the solution is modular and extensible, so that I can easily add new features or capabilities in the future.

 The directory structure of my notes is "notes" folder, then folders for years, and then folders for months. The Markdown files inside of the month folders may have all types of names, the names usually have some context to the content, but some of them may just be titled with the date. The solution should look at all Markdown files in these folders and subfolders to extract TODOs. 

 The GTD plans need to be stored in a mirrored directory structure starting with "plans". Then the years, then the months, and then the plans themselves. The naming convention of the file should make it clear if it's a daily morning plan, a daily afternoon plan, a weekly review, or a weekly plan. For example, the morning plan for June 10th, 2024 could be named "2024-06-10-morning-plan.md", the afternoon plan for the same day could be named "2024-06-10-afternoon-plan.md", the weekly review for the week of June 10th could be named "2024-06-10-weekly-review.md", and the weekly plan for the week of June 10th could be named "2024-06-10-weekly-plan.md".

 Ideally, if the plans could be emailed to me as PDFs, that would be great, but that's a nice to have, though nothing in the initial design should block this as a future enhancement.

 Investigate the use of agent frameworks. Also, please capture all the GTD understanding in some notion of a skills file in markdown. This will allow the understanding of the GTD framwork to be decoupled from the implementation of the TODO Manager agent, and will allow for easier updates and improvements to the GTD understanding in the future.