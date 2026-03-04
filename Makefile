.PHONY: init dashboard clean help

help:
	@echo "Terraform Agent Dashboard Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make init           - Install dashboard dependencies"
	@echo "  make dashboard      - Start the React dashboard development server"
	@echo "  make clean          - Remove node_modules and build artifacts"
	@echo ""

init:
	@echo "Installing dashboard dependencies..."
	cd dashboard && npm install

dashboard: init
	@echo "Starting dashboard development server..."
	@echo "Open http://localhost:5173 in your browser"
	cd dashboard && npm run dev

clean:
	@echo "Cleaning dashboard artifacts..."
	rm -rf dashboard/node_modules dashboard/dist
