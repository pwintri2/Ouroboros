import SwiftUI

struct AgentResponse: Codable {
    let response: String
    let tier: Int
    let status: String
}

struct ContentView: View {
    @State private var inputPrompt: String = ""
    @State private var responseText: String = "Systeem gereed. Hoe kan ik je vandaag helpen?"
    @State private var selectedTier: Int = 3
    @State private var isLoading: Bool = false
    @State private var serverOnline: Bool = false
    
    // --- Document Generator States ---
    @State private var showDiffView: Bool = false
    @State private var pendingFilename: String = ""
    @State private var pendingContent: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header met Status
            HStack {
                Label("Wintrip Agent", systemImage: "bolt.shield.fill")
                    .font(.headline)
                    .foregroundColor(.primary)
                Spacer()
                HStack(spacing: 4) {
                    Circle()
                        .fill(serverOnline ? Color.green : Color.red)
                        .frame(width: 8, height: 8)
                    Text(serverOnline ? (isLoading ? "Bezig..." : "Online") : "Offline")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            
            Divider()

            // AI Tier Picker
            Picker("Selecteer Tier", selection: $selectedTier) {
                Text("Tier 3 (Lokaal)").tag(3)
                Text("Tier 2 (Cloud)").tag(2)
                Text("Tier 1 (High)").tag(1)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .disabled(isLoading)

            // Response Display
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text(responseText)
                        .font(.system(.body, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                }
            }
            .background(Color.secondary.opacity(0.1))
            .cornerRadius(10)
            .frame(height: 250)

            // Input Section
            VStack(spacing: 10) {
                TextField("Typ je opdracht of vraag...", text: $inputPrompt)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit {
                        if !inputPrompt.isEmpty && !isLoading {
                            sendPrompt()
                        }
                    }
                    .disabled(isLoading)

                HStack {
                    Button(action: checkStatus) {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 14, weight: .bold))
                    }
                    .buttonStyle(.plain)
                    .help("Herstel verbinding")

                    Spacer()

                    Button(action: sendPrompt) {
                        if isLoading {
                            ProgressView().controlSize(.small)
                        } else {
                            Text("Verstuur")
                                .fontWeight(.semibold)
                                .frame(width: 80)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isLoading || inputPrompt.isEmpty)
                }
            }
        }
        .padding()
        .frame(width: 400, height: 500)
        .onAppear(perform: checkStatus)
        .sheet(isPresented: $showDiffView) {
            DiffView(filename: $pendingFilename, content: $pendingContent, isPresented: $showDiffView, mainResponse: $responseText)
        }
    }

    // --- Backend Logica ---

    func checkStatus() {
        guard let url = URL(string: "http://127.0.0.1:8000/status") else { return }
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                self.serverOnline = (error == nil)
            }
        }.resume()
    }

    func sendPrompt() {
        guard let url = URL(string: "http://127.0.0.1:8000/process") else { return }
        isLoading = true
        responseText = "Wintrip analyseert je verzoek..."
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["prompt": inputPrompt, "tier": selectedTier]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                self.isLoading = false
                if let error = error {
                    self.responseText = "FOUT: \(error.localizedDescription)"
                    return
                }
                guard let data = data else { return }
                do {
                    let decoded = try JSONDecoder().decode(AgentResponse.self, from: data)
                    let resp = decoded.response
                    
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
                        self.responseText = "Bestand '\(pendingFilename)' staat klaar voor controle."
                    } else {
                        self.responseText = resp
                    }
                    self.inputPrompt = ""
                } catch {
                    self.responseText = "FOUT bij decoderen: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
}

// --- DiffView Component ---
struct DiffView: View {
    @Binding var filename: String
    @Binding var content: String
    @Binding var isPresented: Bool
    @Binding var mainResponse: String
    
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
                    self.mainResponse = "✅ Bestand '\(filename)' succesvol opgeslagen."
                } else {
                    let serverError = (result?["detail"] as? String) ?? "Server weigerde opslag."
                    self.mainResponse = "❌ FOUT: \(serverError)"
                }
                self.isSaving = false
                self.isPresented = false // Altijd sluiten
            }
        } catch {
            DispatchQueue.main.async {
                self.mainResponse = "❌ FOUT: \(error.localizedDescription)"
                self.isSaving = false
                self.isPresented = false // Altijd sluiten
            }
        }
    }
}
