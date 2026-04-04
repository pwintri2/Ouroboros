import SwiftUI

struct ChatMessage: Identifiable, Codable {
    var id = UUID()
    let text: String
    let isUser: Bool
    let timestamp: Date

    init(text: String, isUser: Bool) {
        self.text = text
        self.isUser = isUser
        self.timestamp = Date()
    }
}

struct AgentResponse: Codable {
    let response: String
    let tier: Int
    let status: String
}

struct ContentView: View {
    @StateObject private var network = NetworkManager()

    @State private var inputPrompt: String = ""
    @State private var messages: [ChatMessage] = [
        ChatMessage(text: "Systeem gereed. Hoe kan ik je vandaag helpen?", isUser: false)
    ]
    @State private var selectedModel: String = "gemma2"
    @State private var isLoading: Bool = false

    // Provider Toggles
    @State private var useChatGPT: Bool = false
    @State private var useGemini: Bool = false
    @State private var useClaude: Bool = false
    
    // --- Document Generator States ---
    @State private var showDiffView: Bool = false
    @State private var pendingFilename: String = ""
    @State private var pendingContent: String = ""

    // JULES FIX: Persona data moved here
    let allPersonas = [
        Persona(id: "talle", name: "Talle Wintrip", icon: "crown.fill", description: "De visionair"),
        Persona(id: "developer", name: "Developer", icon: "hammer.fill", description: "De bouwer"),
        Persona(id: "critic", name: "Critic", icon: "eye.trianglebadge.exclamationmark.fill", description: "De scherprechter"),
        Persona(id: "tester", name: "Tester", icon: "checkmark.seal.fill", description: "De kwaliteitscontrole")
    ]

    var body: some View {
        NavigationView {
            // Sidebar (Vergadertafel)
            VStack(alignment: .leading) {
                Text("VERGADERTAFEL")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundColor(.secondary)
                    .padding(.horizontal)
                    .padding(.top)

                List {
                    ForEach(allPersonas) { persona in
                        HStack {
                            Image(systemName: persona.icon)
                                .foregroundColor(network.seatedPersonas.contains(persona.id) ? .blue : .secondary)
                                .frame(width: 25)

                            VStack(alignment: .leading) {
                                Text(persona.name)
                                    .font(.body)
                                    .fontWeight(network.seatedPersonas.contains(persona.id) ? .bold : .regular)
                                Text(persona.description)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }

                            Spacer()

                            // JULES FIX: Functional Invite Toggles
                            Toggle("", isOn: Binding(
                                get: { network.seatedPersonas.contains(persona.id) },
                                set: { newValue in
                                    if newValue {
                                        network.invitePersona(personaId: persona.id)
                                    } else {
                                        network.removePersona(personaId: persona.id)
                                    }
                                }
                            ))
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .controlSize(.mini)
                        }
                        .padding(.vertical, 4)
                    }
                }
                .listStyle(.sidebar)

                Spacer()

                // Status indicator
                HStack {
                    Circle()
                        .fill(network.isOnline ? Color.green : Color.red)
                        .frame(width: 8, height: 8)
                    Text(network.isOnline ? "Online" : "Offline")
                        .font(.caption2)
                    Spacer()
                }
                .padding()
            }
            .frame(minWidth: 250)
            
            // Main Chat View
            VStack(spacing: 0) {
                // Header with Provider Toggles & Model Picker
                HStack {
                    HStack(spacing: 15) {
                        providerToggle(name: "ChatGPT", isOn: $useChatGPT)
                        providerToggle(name: "Gemini", isOn: $useGemini)
                        providerToggle(name: "Claude", isOn: $useClaude)
                    }

                    Spacer()

                    Picker("Model", selection: $selectedModel) {
                        ForEach(network.models, id: \.self) { model in
                            Text(model).tag(model)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 200)
                    .onChange(of: selectedModel) { newValue in
                        network.switchModel(model: newValue)
                    }
                }
                .padding()
                .background(Color.black.opacity(0.05))

                // Messages List
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(messages) { message in
                                ChatBubble(message: message)
                                    .id(message.id)
                            }
                            if isLoading {
                                HStack {
                                    ProgressView().controlSize(.small)
                                    Text("Wintrip denkt na...")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Spacer()
                                }
                                .padding(.horizontal)
                                .id("loading_indicator")
                            }
                        }
                        .padding()
                    }
                    .onChange(of: messages.count) { _ in
                        withAnimation {
                            proxy.scrollTo(messages.last?.id, anchor: .bottom)
                        }
                    }
                    .onChange(of: isLoading) { newValue in
                        if newValue {
                            withAnimation {
                                proxy.scrollTo("loading_indicator", anchor: .bottom)
                            }
                        }
                    }
                }

                Divider()

                // Input Area
                HStack(spacing: 12) {
                    TextField("Typ je opdracht of vraag...", text: $inputPrompt)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit {
                            if !inputPrompt.isEmpty && !isLoading {
                                sendPrompt()
                            }
                        }
                        .disabled(isLoading)

                    Button(action: sendPrompt) {
                        Image(systemName: "paperplane.fill")
                            .font(.headline)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isLoading || inputPrompt.isEmpty)
                }
                .padding()
            }
        }
        .frame(minWidth: 900, minHeight: 700)
        .onAppear {
            network.checkStatus()
            network.fetchModels()
            network.fetchTableState()
        }
        .sheet(isPresented: $showDiffView) {
            DiffView(filename: $pendingFilename, content: $pendingContent, isPresented: $showDiffView, mainResponse: Binding(
                get: { messages.last?.text ?? "" },
                set: { messages.append(ChatMessage(text: $0, isUser: false)) }
            ))
        }
    }

    @ViewBuilder
    func providerToggle(name: String, isOn: Binding<Bool>) -> some View {
        HStack(spacing: 4) {
            Text(name)
                .font(.caption)
            Toggle("", isOn: isOn)
                .toggleStyle(.switch)
                .labelsHidden()
                .controlSize(.mini)
                .onChange(of: isOn.wrappedValue) { newValue in
                    // JULES FIX: Wire provider toggles to model state
                    if newValue {
                        // Ensure exclusive selection if desired, or just set model
                        if name == "ChatGPT" { selectedModel = "chatgpt" }
                        if name == "Gemini" { selectedModel = "gemini" }
                        if name == "Claude" { selectedModel = "claude" }
                        network.switchModel(model: selectedModel)
                    }
                }
        }
    }

    // --- Backend Logica ---

    func sendPrompt() {
        guard let url = URL(string: "http://127.0.0.1:8000/process") else { return }
        isLoading = true
        let userMsg = inputPrompt
        messages.append(ChatMessage(text: userMsg, isUser: true))
        inputPrompt = ""
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // JULES FIX: Ensure correct provider/model parameter is sent to backend
        var activeModel = selectedModel
        if useChatGPT { activeModel = "chatgpt" }
        else if useGemini { activeModel = "gemini" }
        else if useClaude { activeModel = "claude" }

        // JULES FIX: Enriched system prompt with persona data for "Vergadertafel"
        let seatedInfo = network.seatedPersonas.isEmpty ? "" : " Deelnemers aan tafel: \(network.seatedPersonas.joined(separator: ", "))."

        let body: [String: Any] = [
            "prompt": userMsg,
            "model": activeModel,
            "system_prompt": "Je bent Wintrip.\(seatedInfo)"
        ]

        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                self.isLoading = false
                if let error = error {
                    self.messages.append(ChatMessage(text: "FOUT: \(error.localizedDescription)", isUser: false))
                    return
                }
                guard let data = data else { return }
                do {
                    let decoded = try JSONDecoder().decode(AgentResponse.self, from: data)
                    let resp = decoded.response
                    
                    // JULES FIX: Handle protocol parsing for file generator
                    // --- Protocol Parsing: [[WINTRIP_FILE]] ---
                    if resp.contains("[[WINTRIP_FILE]]") {
                        let lines = resp.components(separatedBy: "\n")
                        for line in lines {
                            if line.hasPrefix("FILENAME:") {
                                self.pendingFilename = line.replacingOccurrences(of: "FILENAME:", with: "").trimmingCharacters(in: .whitespaces)
                            }
                        }
                        if let contentRange = resp.range(of: "CONTENT:") {
                            self.pendingContent = String(resp[contentRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
                        }
                        self.showDiffView = true
                    } else {
                        self.messages.append(ChatMessage(text: resp, isUser: false))
                    }
                } catch {
                    self.messages.append(ChatMessage(text: "FOUT bij decoderen: \(error.localizedDescription)", isUser: false))
                }
            }
        }.resume()
    }
}

struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.isUser { Spacer() }

            VStack(alignment: message.isUser ? .trailing : .leading) {
                Text(message.text)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(message.isUser ? Color.blue : Color.gray.opacity(0.2))
                    .foregroundColor(message.isUser ? .white : .primary)
                    .cornerRadius(16)
                    .textSelection(.enabled)

                Text(message.timestamp, style: .time)
                    .font(.system(size: 8))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 4)
            }

            if !message.isUser { Spacer() }
        }
    }
}

// --- DiffView Component ---
struct DiffView: View {
    @Binding var filename: String
    @Binding var content: String
    @Binding var isPresented: Bool
    @Binding var mainResponse: Binding<String>
    
    @State private var isSaving: Bool = false

    var body: some View {
        VStack(spacing: 15) {
            HStack {
                Image(systemName: "doc.badge.plus")
                    .font(.system(size: 24))
                    .foregroundColor(.orange)
                VStack(alignment: .leading) {
                    Text("Nieuw bestand voor controle")
                        .font(.headline)
                    Text(filename)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                Spacer()
            }
            .padding(.top)
            
            Divider()
            
            ScrollView {
                Text(content)
                    .font(.system(.body, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
                    .background(Color.orange.opacity(0.05))
                    .cornerRadius(8)
            }
            
            HStack {
                Button("Annuleren") {
                    isPresented = false
                }
                .keyboardShortcut(.escape, modifiers: [])
                .disabled(isSaving)
                
                Spacer()
                
                Button(action: {
                    Task {
                        await saveFile()
                    }
                }) {
                    if isSaving {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Opslaan in /output/")
                            .fontWeight(.bold)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.orange)
                .disabled(isSaving)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(.bottom)
        }
        .padding()
        .frame(width: 550, height: 450)
    }
    
    func saveFile() async {
        guard let url = URL(string: "http://127.0.0.1:8000/commit_save") else { return }
        isSaving = true
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "filename": filename,
            "content": content
        ]
        
        do {
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: request)
            
            let isSuccess = (response as? HTTPURLResponse)?.statusCode == 200
            let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            
            DispatchQueue.main.async {
                if isSuccess && result?["status"] as? String == "Success" {
                    self.mainResponse.wrappedValue = "✅ Bestand '\(filename)' succesvol opgeslagen."
                } else {
                    let serverError = (result?["detail"] as? String) ?? "Server weigerde opslag."
                    self.mainResponse.wrappedValue = "❌ FOUT: \(serverError)"
                }
                self.isSaving = false
                self.isPresented = false // Altijd sluiten
            }
        } catch {
            DispatchQueue.main.async {
                self.mainResponse.wrappedValue = "❌ FOUT: \(error.localizedDescription)"
                self.isSaving = false
                self.isPresented = false // Altijd sluiten
            }
        }
    }
}
