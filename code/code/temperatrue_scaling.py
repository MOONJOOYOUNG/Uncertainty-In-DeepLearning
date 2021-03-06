
# ModelWithTemperature
class ModelWithTemperature(nn.Module):
    def __init__(self, model):
        super(ModelWithTemperature, self).__init__()
        self.model = model

    def forward(self, input):
        logits, feature = self.model(input)
        return self.temperature_scale(logits), feature
    # auto find_temperature_scale
    def find_temperature_scale(self, logits, tm):
        return logits / tm
    # set temperature
    def set_temperature(self, tm):
        self.temperature = nn.Parameter(torch.ones(1) * tm)

    def temperature_scale(self, logits):
        temperature = self.temperature.unsqueeze(1).expand(logits.size(0), logits.size(1)).cuda()

        return logits / temperature
    # find temperature & optimize
    def calc_temperature(self, valid_loader):
        self.cuda()
        nll_criterion = nn.CrossEntropyLoss().cuda()
        ece_criterion = _ECELoss().cuda()

        # First: collect all the logits and labels for the validation set
        logits_list = []
        labels_list = []
        with torch.no_grad():
            for input, label, idx in valid_loader:
                input = input.cuda()
                label = label.cuda()
                logits,feature = self.model(input)
                logits_list.append(logits)
                labels_list.append(label)
            logits = torch.cat(logits_list).cuda()
            labels = torch.cat(labels_list).cuda()

        # Calculate NLL and ECE before temperature scaling
        before_temperature_nll = nll_criterion(logits, labels).item()
        before_temperature_ece = ece_criterion(logits, labels).item()
        print('Before temperature - NLL: %.6f, ECE: %.6f' % (before_temperature_nll, before_temperature_ece))

        ece_li = []
        temperature_li = []
        # 최적 값 범위 설정. (0.1 ~ 5 사이)  --- 0.1 보다 작아선 안(Nan error).
        linspace = list(np.linspace(0.1, 5, 100))
        print('Find temperature')
        for i in linspace:
            print('temperature : ',i)
            after_temperature_nll = nll_criterion(self.find_temperature_scale(logits, i), labels).item()
            after_temperature_ece = ece_criterion(self.find_temperature_scale(logits, i), labels).item()
            print('After temperature - NLL: %.6f, ECE: %.6f' % (after_temperature_nll, after_temperature_ece))
            ece_li.append(after_temperature_ece)
            temperature_li.append(i)
        # temperature min index
        idx = np.argmin(ece_li)
        # 최소 ece 값에 해당하는 temperature 값 설정.
        self.set_temperature(temperature_li[idx])
        print('-------------------------------------------------')
        print('Set temperature: %.6f' % temperature_li[idx])

        # temperature optimize.
        optimizer = optim.LBFGS([self.temperature], lr=0.01, max_iter=100)
        def eval():
            loss = nll_criterion(self.temperature_scale(logits), labels)
            loss.backward()
            return loss
        optimizer.step(eval)

        after_temperature_nll = nll_criterion(self.temperature_scale(logits), labels).item()
        after_temperature_ece = ece_criterion(self.temperature_scale(logits), labels).item()
        print('-------------------------------------------------')
        print('Optimal temperature: %.6f' % self.temperature.item())
        print('After temperature - NLL: %.6f, ECE: %.6f' % (after_temperature_nll, after_temperature_ece))
