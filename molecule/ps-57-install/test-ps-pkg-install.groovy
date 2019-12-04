pipeline {
  agent {
    label 'micro-amazon'
  }
  options { disableConcurrentBuilds() }
  environment {
    PATH='/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin:/home/ec2-user/.local/bin'
    ROLE_NAME='ps-57-install'
  }
  parameters {
    choice(
      name: 'PLATFORM',
      description: 'Test distribution',
      choices: [
        'centos-7',
        'debian-9',
        'debian-10',
        'ubuntu-18.04',
        'rhel8'
      ]
    )
    choice(
      name: 'INSTALL_REPO',
      description: 'Repo for package install',
      choices: [
        'testing',
        'experimental',
        'main',
      ]
    )
  }
  stages {
    stage('Set build name'){
      steps {
        script {
          currentBuild.description = "${PLATFORM}-${INSTALL_REPO}"
        }
      }
    }
    stage ('Setup Environment Variables') {
      steps {
        script {
          vms = readYaml (file: 'molecule/configuration.yml')
          env.IMAGE = vms."${PLATFORM}".image
          env.USER = vms."${PLATFORM}".user
          env.SUBNET = vms."${PLATFORM}".subnet
          env.AWS_DEFAULT_REGION = vms."${PLATFORM}".aws_default_region
          env.INSTANCE_TYPE = vms."${PLATFORM}".instance_type
        }
      }
    }
    stage ('Prepare') {
      steps {
        checkout scm
        sh '''
            sudo yum install -y gcc python3-pip python3-devel libselinux-python openssl-devel
            sudo mkdir -p /usr/local/lib64/python3.7/site-packages
            sudo rsync -aHv /usr/lib64/python2.7/site-packages/*selinux* /usr/local/lib64/python3.7/site-packages/
            pip3 install --user pytest molecule ansible wheel boto boto3 paramiko selinux 'molecule[ec2]'
        '''
        withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'AMI/OVF', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
          sh '''
              cd molecule/${ROLE_NAME}
              python3 -m molecule list
              python3 -m molecule destroy -s ec2 || true
              if [ -d ~/.cache/molecule/${ROLE_NAME} ]; then
                rm -rf ~/.cache/molecule/${ROLE_NAME}
              fi
          '''
        }
      }
    }
    stage ('Create virtual machines') {
      steps {
        withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'AMI/OVF', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
          sh '''
              echo $USER
              echo $REGION
              echo $SUBNET
              echo $IMAGE
              echo $PLATFORM
              cd molecule/${ROLE_NAME}
              python3 -m molecule list
              python3 -m molecule create -s ec2
              python3 -m molecule list
          '''
        }
      }
    }
    stage ('Run playbook for test') {
      steps {
        sh '''
            cd molecule/${ROLE_NAME}
            python3 -m molecule list
            python3 -m molecule converge -s ec2
        '''
      }
    }
    stage ('Start testinfra tests') {
      steps {
        sh '''
            cd molecule/${ROLE_NAME}
            python3 -m molecule list
            python3 -m molecule verify -s ec2
        '''
        junit 'molecule/${ROLE_NAME}/molecule/ec2/*.xml'
      }
    }
    stage ('Start packages deletion') {
      steps {
        sh '''
            cd molecule/${ROLE_NAME}
            python3 -m molecule list
            python3 -m molecule cleanup -s ec2
        '''
      }
    }
  }
  post {
    always {
      withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'AMI/OVF', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
        sh '''
            cd molecule/${ROLE_NAME}
            python3 -m molecule list
            python3 -m molecule destroy -s ec2
        '''
      }
    }
  }
}
