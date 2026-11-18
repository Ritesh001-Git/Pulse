## AI Prompts to Open Code

#### 1. Initial Plan and My Architecture Design
So we are building a platform called Pulse, a service monitoring and incident management platform that continuously monitors services, detects failures, create and track incident until recovery, keep customer updated through a public status page. And also track service reliability and keep the engineering team and the support team updated. My proposed architecture is a front end using React where the engineers can see and add the services. And there will be section for incident management, reliability metrics, a seperate page for the public status. And backend using FastAPI, a monitoring engine continuously check registered services and detect failure or degradation. And an incident engine manage incident creation, acknowledgement, timeline and recovery. And notification engine that will notify the engineers support team and customers. So before start coding, let's plan a complete project. Create a plan.md file with the component breakdown, API design, what API do we need and evaluate my proposed architecture. Suggest anything missing. And this is only the planning phase, so no coding or implementation yet

#### 2. Frontend Plan Prompt
Okay, let's first build the front end for Pulse using React, a clean modern dashboard design. I want Pulse to look like a professional monitoring and incident management platform. So build the main UI with the following pages: like first overview dashboard showing total services, healthy services, degraded services, down services, active services. Then services page showing up monitored services with their status, owner, response time, and availability. Service detail page showing health history, response time, uptime reliability target and recent incident. Incident page showing current and past incident with status, severity and duration. And incident detail page should have a timeline, acknowledgement button and a notes section where the engineers can add notes and a separate public status page showing the current status of all the services. And if a status, if a service goes down, it will inform the users that the service is down from our side. So customer can ensure transparency during incidents. And use reusable React component, a sidebar navigation bar, chart tables. And for now use mock data. We will later replace it with actual data when we'll create the database and backend layer. And don't put the entire application into one component. Create a proper component and page structure. First show me the front-end structure and design approach. Then implement it and keep the UI consistent for all the pages

#### 3. Prompt to test the frontend
So before we start building backend and the database, evaluate that this frontend is actually ready for the real-world API integration. The current component, data fetch status, services are designed properly for dynamic backend data. And propose an API response structure and frontend changes needed to make the integration clean. And identify mock data dependencies, missing loading or error state, or inconsistencies that could create integration problems.

#### 4. Instruct the AI to change some architecture decision and test again
Okay, you identify some integration issue. But before implementing the refactor, let's reconsider a few architecture decision like fix the state incident state bug and reusable loading error empty and ensure acknowledgement and notes update the UI consistently. And use a TanStack query instead of building a custom API management system. 

And after implementing all of this, run the application and test the, all the pages navigation, loading error states and responsiveness. And report what was actually tested and any remaining limitation

#### 5. Prompt to build the Database
Okay let's build database model using PostgreSQL. So use PostgreSQL with SQLAlchemy. And I need database model for users with id, email, name, role, password. Then services: id, name, description, URL, health path, check interval, timeout, degraded latency, failure threshold, team owner, is active, created at. Then check result with id, service id, checked at, status up, degraded, down, then latency, status code error. Incident with id, service id, title, state, acknowledgement, opened at, resolved at, reopened. Then for timeline events: id, incident id, at actor. Then for notification: id, at, channel, audience, incident id, event status detail and maintenance window: id, server id, start at, end at, reason And make sure the relationships between timestamp indexes and constraints are designed properly. We should be able to store historical incident for a service while preventing duplicate active incident. So create a database configuration, SQLAlchemy models and also create a sample database health check endpoint and inspect the existing code integrate with it

#### 6. Counter Question to test the database
Suppose if any feature database connection drops or timeout mid-request, will it crash that particular service or the whole application, or it will fail gracefully?

#### 7. Identified and told AI what to fix 
Before we build the backend layer, add a proper DB error response. Safe retry for failures, connection and command timeout. And make sure future monitoring loop can survive temporary database outage without crashing. And test the failure scenarios and report what you fixed and what the current situation is

#### 8. Backend Prompt
So now let's implement the main backend APIs using FastAPI. Use the PostgreSQL database and the models that we already created. And use this API design from the plan.md. And we have to test the application against the Pulse starter kit that has a Docker compose file with some mock services like quotes, payment, claims, and notification. And also read the README.md file inside the pulse starter kit and create the backend according to that And connect the front end service page to this APIs. Replace the mock data and mock services with real backend data. And don't implement the monitoring scheduler yet. We will do that in later stages. And test the APIs fix any integration issue before moving forward

#### 9. Challenged AI approach with my approach
So before going ahead, suppose a service has a mixed failure response like two down checks followed by degraded check while using only the latest check to decide incident severity, always be reliable. I think this could sometimes classify incidents incorrectly. So can you review this approach, test different failure scenarios, and Instead of deciding only from one latest check, what if we use worst state like consecutively check threshold? For example, if an outage has already been detected, a later degraded check shouldn't downgrade its severity. So can you evaluate whether this is a better approach? Compare it with your current implementation and test different sequence such as down, degraded to down. And identify some edge cases

Comparison summary
Aspect	Old (latest-only)	New (worst-in-streak)
down,down,degraded	❌ degradation	✅ outage
downgrade protection	❌ none	✅ monotonic within streak
escalation (degradation → outage)	❌ never	✅ with timeline event
streak boundary correctness	❌ window crosses ups	✅ reset at up
query cost	1 bounded query	2 small indexed queries

#### 10. Incident management, notifications and reliability
We can now implement the remaining incident management and the reliability feature. Ensure incident automatically resolve after the configured recovery threshold. Handle reopen versus new incident correctly and maintain a complete incident timeline. Implement notification for incident creation, incident creation, acknowledgement updates and resolution including retries, failure. Complete availability uptime latency . Test the complete incident and notification lifecycle, including failure scenarios.

#### 11. Full integration, testing and final polish
Now review Pulse as a complete application. Fix all integration bugs, UI issues, and missing edge cases. Specifically, fix the **Register Service button**—it currently appears static and doesn't work. Implement the complete registration flow, including the form, validation, API integration, database persistence, success/error feedback, and automatic inclusion of newly registered services in monitoring. Verify that authentication, scheduler, incidents, notifications, metrics, and public status page work together. Run end-to-end tests, fix issues, polish the UI, and update the README with setup instructions, features, and demo credentials. Report test results and remaining limitations.

#### 12. Progress.md and Design.md
Create `progress.md` to document completed tasks and overall progress. Additionally, create `design.md` to outline the platform's architecture, features, and other relevant details.

#### 13. Prompt to create a .gitignore file
Create a .gitignore file and list all files that should not be pushed to GitHub, such as the env file, virtual environment files, or any other unnecessary files from the frontend, backend, or elsewhere.