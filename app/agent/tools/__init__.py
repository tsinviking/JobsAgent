from app.agent.tools.skill_analysis import SkillAnalysisTool
from app.agent.tools.email_notifier import EmailNotifier
from app.agent.tools.web_research import WebResearchTool


class ToolRegistry:
    def __init__(self):
        self.skill_analysis = SkillAnalysisTool()
        self.email = EmailNotifier()
        self.web_research = WebResearchTool()
