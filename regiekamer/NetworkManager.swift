import SwiftUI
import Combine

struct Persona: Identifiable, Codable {
    let id: String
    let name: String
    let icon: String
    let description: String
}

class NetworkManager: ObservableObject {
    @Published var models: [String] = ["gemma2", "llama3.1"]
    @Published var isOnline: Bool = false
    @Published var isLoading: Bool = false
    @Published var seatedPersonas: [String] = []

    // JULES FIX: Add support for diff view content
    @Published var diffFileContent: String? = nil
    @Published var pendingFilename: String = ""

    private let baseURL = "http://127.0.0.1:8000"

    func checkStatus() {
        guard let url = URL(string: "\(baseURL)/status") else { return }
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                self.isOnline = (error == nil)
            }
        }.resume()
    }

    func fetchModels() {
        guard let url = URL(string: "\(baseURL)/models") else { return }
        URLSession.shared.dataTask(with: url) { data, response, error in
            guard let data = data else { return }
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: [String]] {
                    DispatchQueue.main.async {
                        // JULES FIX: Merge local models with cloud providers if needed
                        var allModels = json["models"] ?? []
                        let cloudProviders = ["chatgpt", "gemini", "claude", "groq"]
                        for provider in cloudProviders {
                            if !allModels.contains(provider) {
                                allModels.append(provider)
                            }
                        }
                        self.models = allModels
                    }
                }
            } catch {
                print("Error fetching models: \(error)")
            }
        }.resume()
    }

    func switchModel(model: String) {
        guard let url = URL(string: "\(baseURL)/model/switch") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["model": model]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request).resume()
    }

    func fetchTableState(tableId: String = "central") {
        guard let url = URL(string: "\(baseURL)/vergadertafel/\(tableId)") else { return }
        URLSession.shared.dataTask(with: url) { data, response, error in
            guard let data = data else { return }
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let seated = json["seated"] as? [String] {
                    DispatchQueue.main.async {
                        self.seatedPersonas = seated
                    }
                }
            } catch {
                print("Error fetching table state: \(error)")
            }
        }.resume()
    }

    func invitePersona(personaId: String, tableId: String = "central") {
        guard let url = URL(string: "\(baseURL)/vergadertafel/invite") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["persona_id": personaId, "table_id": tableId]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request) { _, _, _ in
            self.fetchTableState(tableId: tableId)
        }.resume()
    }

    func removePersona(personaId: String, tableId: String = "central") {
        guard let url = URL(string: "\(baseURL)/vergadertafel/remove") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["persona_id": personaId, "table_id": tableId]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request) { _, _, _ in
            self.fetchTableState(tableId: tableId)
        }.resume()
    }
}
