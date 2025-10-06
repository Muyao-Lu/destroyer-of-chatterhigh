

function main() {

    const mode = "deployment"
    const errors = ["Error! You aren't signed in!", "Source was not deemed safe. Aborting question!"]
    let listener_ids = []

    let choices = {}
    let question = ""
    let endpoint

    if (mode == "deployment"){
        endpoint = "https://destroyer-of-chatterhigh.vercel.app/"
    }
    else{
        endpoint = "http://127.0.0.1:8000/"
    }
    

    let processing = false

    function validate_question_open(){
        return ((!( document.getElementById("click-url") === null)) && (! (document.getElementById("answer-submit") === null)))
    }

    function validate_dashboard_open(){
        return (!(document.getElementById("automation-dashboard") === null))
    }

    function create_dashboard(){
        const h = document.getElementsByTagName("head")[0];
        const b = document.getElementsByTagName("body")[0];

        const dashboard_container = document.createElement("div");
        dashboard_container.id = "automation-dashboard-container"

        const dashboard = document.createElement("div");
        dashboard.id = "automation-dashboard";
        dashboard.innerHTML = `
            <h2>Automation dashboard</h2>

            <img src="https://raw.githubusercontent.com/Muyao-Lu/destroyer-of-chatterhigh/main/static/glorious_king_fred.png?raw=true">
            <p id="error-reporter">Errors will pop up here:</p>
            <button id="automation-end-button">End Automation</button>`

        const styles = document.createElement("style");
        styles.innerHTML = `
            #automation-dashboard{
                width: max(20vw, 200px);
                position: fixed;
                bottom: 0;
                right: 0;
                z-index: 10000000;
                /* background-color: rgba(0, 0, 0, 0.4);
                border: 2px solid white; */
            }

            #automation-dashboard-container{
                width: 80vw;
                position: fixed;
                bottom: 0;
                right: 0;
            }
                
            #automation-dashboard h2{
                color: white;
                font-family: monospace;
                font-size: max(18px, 2vmin);
                text-align: center;
                width: 100%;
                border-radius: 10px;
                border: 2px solid white;
                background-color: rgba(0, 0, 0, 0.4);

            }
                
            #automation-dashboard img {
                width: 60%;
                position: relative;
                margin: 10px 20%;

            }
                
            #automation-summary #confirm, #automation-dashboard #automation-end-button {
                width: 70%;
                margin: 0 15%;
                background-color: rgb(56, 182, 255);
                border: 4px solid white;
                border-radius: 10px;
                height: 20%;
                color: white;
                font-family: monospace;

            }
                
            #automation-summary {
                margin-bottom: 10%;
                background-color: white;
                border: 3px solid black;
                margin-right: 5%;
                width: 60%;
                padding: 3vmin;
                border-radius: 20px 20px 0 20px;
                overflow-y: scroll;
                z-index: 100000000;
                position: fixed;
                right: 12%;
                bottom: 10%;
                height: 50vh;

            }
                
            #automation-summary #summary-header{
                font-size: max(20px, 2vmin);
                color: black;
                font-family: monospace;
            }
                
            #automation-summary br{
                display: block;
            }
                
            #automation-dashboard #error-reporter{
                width: 80%;
                margin: 10%;
                border: 2px solid white;
                border-radius: 5px;
                background-color: black;
                font-family: monospace;
                color: white;
                padding: 3%;
            }`

            


        h.appendChild(styles);
        dashboard_container.appendChild(dashboard);
        b.appendChild(dashboard_container);

        document.getElementById("automation-end-button").addEventListener("click", end_automation)

        
    }

    function end_automation(){
        for (let item of listener_ids){
            clearInterval(item);
        }

        document.getElementById("automation-dashboard-container").remove();
        chrome.runtime.sendMessage({
            action: "end_automation"
        });

    }

    function answer_question(){
        if (validate_question_open()){
            if (! processing){
                processing = true;
                ids = document.querySelectorAll("input[type='radio']")

            
                for (let item of ids){
                    choices[item.id] = document.querySelector("label[for='" + item.id + "']").innerHTML;
                }
                question = document.getElementsByClassName("body")[0].innerHTML;

                get_session_id(function(response){solve_question_request(response, choices, question)});
            }
            
            
        }
        
    }

    function solve_question_request(session_id, choices, question){

        const data = JSON.stringify({
        'choices': choices,
        'question': question,
        'website_link': document.querySelector("#click-url").href,
        'session_token': session_id.value
        });
        
        if (! (document.querySelector("#click-url").href == "https://resources.chatterhigh.com/chatterhigh-survey-question-page")){
            let request = new XMLHttpRequest();
            
            request.open('POST', endpoint);
            request.setRequestHeader('Content-Type', 'application/json');

            request.onreadystatechange = function (){
                console.log("Initiated request");
                if (this.readyState == 4){
                    console.log(this.responseText == "null")
                    if (! (this.responseText.replace(/"/g, "") in errors) && ! (this.responseText == "null")){
                        console.log(this.responseText);
                        select_choice(this.responseText);
                        chrome.storage.local.set({
                            last_correct_text: choices[this.responseText.replace(/"/g, "")],
                            last_question: question
                        });
                        chrome.storage.local.set({summary_needed: true})
                        document.getElementById("answer-submit").click();
                    }
                    else if (this.responseText == "null"){
                        document.getElementById("error-reporter").innerHTML = "The backend is currently down. Please try again in a bit"
                    }
                    else{
                        document.getElementById("error-reporter").innerHTML = this.responseText.replace(/"/g, "")
                    }


                }
            }

            request.send(data);
        }
        else{
            first = Object.keys(choices)[0]
            select_choice(first);
            document.getElementById("answer-submit").click();
        }
        
    }

    function add_question_to_bank(question){
        let current_questions_list
        chrome.storage.local.get(["question_array"], function(result){
            current_questions_list = result.question_array;
            console.log("Current Questions " + current_questions_list)
            if (! (current_questions_list === undefined)){
                current_questions_list.push(question);
                
            }
            else{
                current_questions_list = [question]
            }
            chrome.storage.local.set({question_array: current_questions_list})
        });

    }

    function clear_bank(){
        chrome.storage.local.set({question_array: []})
    }

    function get_quiz_finished(){
        const items = document.getElementsByTagName("p");

        for (let item of items){
            if (item.innerHTML === "Correct Answers"){
                for (let item of items){
                    if (item.innerHTML === "Points Earned" || item.innerHTML === "Research Questions"){
                        return true
                    }
                }
            }

        }
        return false
    }

    function request_summary(result){
            console.log(result.summary_needed);
            if ((! (result.question_array === undefined)) && result.question_array.length > 0 && result.summary_needed){
                chrome.storage.local.set({summary_needed: false})
                let data = JSON.stringify({
                    "text": result.question_array
                })
                
                let request = new XMLHttpRequest();
                const new_endpoint = endpoint + "summarize"
                
                request.open('POST', new_endpoint);
                request.setRequestHeader('Content-Type', 'application/json');

                request.onreadystatechange = function (){
                    if (this.readyState == 4){
                        console.log(this.responseText)
                        const container = document.querySelector("#automation-dashboard-container");

                        const summary_div = document.createElement("div");
                        summary_div.id = "automation-summary"
                        summary_div.innerHTML = `
                        <h1 id="summary-header">- Summary -</h1>
                        <p>` + this.responseText.replace(/"/g, "") + `</p>
                        <button id="confirm">Confirm that I read the summary (Or not. IDC)</button>`
                        container.appendChild(summary_div);
                        document.querySelector("#confirm").addEventListener("click", function(){document.querySelector("#automation-summary").remove()});
                        clear_bank();


                    }
                }

                request.send(data);
            }
        
    
    }

    function select_choice(id){
        document.getElementById(id.replace(/"/g, "")).checked = true;
    }

    function initiate_program(){
        if (window.location.hostname == "chatterhigh.com" || window.location.hostname == "www.chatterhigh.com"){
            create_dashboard();
            listener_ids.push(setInterval(answer_question, 100));
            listener_ids.push(setInterval(answer_subjective_question, 100));
            listener_ids.push(setInterval(function(){if (get_quiz_finished()){
                chrome.storage.local.get(["question_array", "summary_needed"], 
                    function(result){request_summary(result)})}}, 1000)
                );

            listener_ids.push(setInterval(function(){if (! validate_dashboard_open()){create_dashboard()}}, 100));
        }
    }
        
        

    function get_session_id(callback) {
        chrome.runtime.sendMessage({
            action: "get_cookie",
            name: "_chatterhigh_session_1",
            url: "https://chatterhigh.com"
        }, function(response){callback(response)});
    }

    function report_correct_answer(){
        for (let item of document.querySelectorAll(".text")){
            if (item.innerHTML === "Correct!"){
                chrome.storage.local.get(["last_correct_text", "last_question"], function (result){
                    if (! (result.last_correct_text === undefined) && ! (result.last_question === undefined)){
                        add_question_to_bank(result.last_question)
                        let new_endpoint = endpoint + "report_correct_answer?question=" + result.last_question + "&correct_answer=" + result.last_correct_text;

                        let request = new XMLHttpRequest();
                        
                        request.open('GET', new_endpoint);
                        request.setRequestHeader('Content-Type', 'application/json');
                        request.send();
                    }
                });
                    
            
            }
        }
        
    }

    function answer_subjective_question(){
        if (get_subjective_question_open()){
            document.querySelector("#question_rating_institute_knowledge_1").checked = true;
            document.querySelector("#question_rating_institute_rating_4").checked = true;
            document.querySelector("#question_rating_category_knowledge_1").checked = true;
            document.querySelector("#question_rating_category_rating_4").checked = true;

            for (let item of document.querySelectorAll(".v2-btn.primary")){
                if (item.value === "Next Question"){
                    item.click();
                }
            }
        }
        

    }

    function get_subjective_question_open(){
        for (let item of document.querySelectorAll(".v2-btn.primary")){
            if (item.value === "Next Question"){
                return true
            }
        }
        return false
    }
    
    setTimeout(initiate_program, 100);
    setTimeout(report_correct_answer, 100);
    
    
}

function reload(tabId, changeInfo, tab){
    if (changeInfo.status === "complete"){
        chrome.scripting.executeScript({
        target: { tabId: tab.id },
        function: main
        });       
    }
  
}

function initiate(tab){
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: main
    });
    
    if (! chrome.tabs.onUpdated.hasListener(reload)) {
        chrome.tabs.onUpdated.addListener(reload);
    }
}

chrome.action.onClicked.addListener(initiate);



chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "get_cookie") {
    chrome.cookies.get({
      url: msg.url,
      name: msg.name
    }, function(cookie) {
      if (cookie) {
        sendResponse({ value: cookie.value });
      } else {
        sendResponse({ value: null });
      }
    });
    return true;
  }
  else if (msg.action === "end_automation") {
    chrome.tabs.onUpdated.removeListener(reload);
  }
});